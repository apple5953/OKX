import unittest
from unittest.mock import patch

import pandas as pd

import server
from server_core.engine import active_unprotected_trades, build_live_trade_snapshot
from server_core.execution import (
    _algo_has_take_profit_and_stop_loss,
    _algo_identifier_matches,
    protection_algos_cover_size,
)
from server_core.okx_client import _build_scan_universe_from_tickers
from server_core.strategies import strategy_category_permission
from server_core.utils import has_valid_protection


def sample_frame(count=60, start=100.0):
    rows = []
    for i in range(count):
        close = start + i * 0.02
        rows.append({
            'timestamp': 1_700_000_000_000 + i * 300_000,
            'time': pd.Timestamp('2026-01-01') + pd.Timedelta(minutes=5 * i),
            'open': close - 0.03,
            'high': close + 0.10,
            'low': close - 0.10,
            'close': close,
            'volume': 1000.0,
            'rsi': 50.0,
            'ema50': close - 0.05,
            'vol_ma': 900.0,
            'bb_mid': close - 0.15,
            'bb_upper': close + 0.50,
            'bb_lower': close - 0.50,
            'macd_hist': 0.1,
            'kc_upper': close + 0.35,
            'kc_lower': close - 0.35,
            'bb_width': 1.0,
            'kc_width': 1.2,
            'is_squeezed': True,
            'adx': 25.0,
        })
    return pd.DataFrame(rows)


class StrategyV6Tests(unittest.TestCase):
    def test_direct_setup_uses_structure_reference_for_entry_zone(self):
        df = sample_frame()
        setup = server.build_direct_mode_setup(
            df,
            'bullish',
            'test',
            entry_reference=99.5,
            stop_reference=98.8,
            target_reference=101.5,
        )
        self.assertLess(setup.prz_center, df['close'].iloc[-1])
        self.assertLessEqual(setup.prz_low, 99.5)
        self.assertGreaterEqual(setup.prz_high, 99.5)
        self.assertEqual(setup.stop_reference, 98.8)

    def test_risk_cap_limits_expected_u_loss(self):
        leverage = server.risk_based_leverage_cap(60.0, 0.008, 0.001)
        expected_loss = 60.0 * leverage * (0.008 + server.ROUND_TRIP_TAKER_RATE + 0.001)
        self.assertLessEqual(expected_loss, server.MAX_PLANNED_LOSS_USDT)
        self.assertGreaterEqual(leverage, 1)

    def test_adaptive_exit_keeps_structure_and_caps_distance(self):
        plan = {
            'sl': 97.0,
            'tp1': 106.0,
            'structural_stop': 98.0,
            'structural_target': 102.0,
        }
        optimizer = {'state': 'train'}
        result = server.apply_adaptive_exits(plan, 'MacroSniper', 100.0, 'bullish', 0.006, optimizer)
        self.assertLess(result['sl'], 100.0)
        self.assertGreater(result['tp1'], 100.0)
        self.assertAlmostEqual(result['sl'], 98.0)
        self.assertGreaterEqual(result['tp_dist_pct'], result['sl_dist_pct'] * 1.25 - 0.00001)

    def test_merge_preserves_all_protection_ids_and_versions(self):
        existing = {
            'status': 'active', 'strategy': 'MacroSniper', 'direction': 'short',
            'protection_order_id': 'a', 'strategy_version': server.STRATEGY_VERSION,
        }
        incoming = {
            'status': 'active', 'strategy': 'MacroSniper', 'direction': 'short',
            'protection_order_id': 'b', 'strategy_version': server.STRATEGY_VERSION,
        }
        server.merge_active_trade(existing, incoming)
        self.assertEqual(existing['protection_order_ids'], ['a', 'b'])
        self.assertEqual(existing['strategy_version'], server.STRATEGY_VERSION)

    def test_universe_excludes_non_crypto_and_stable_pairs(self):
        crypto = {'swap': True, 'quote': 'USDT', 'settle': 'USDT', 'base': 'BTC', 'info': {'instCategory': '1'}}
        stock = {'swap': True, 'quote': 'USDT', 'settle': 'USDT', 'base': 'NVDA', 'info': {'instCategory': '3'}}
        gold = {'swap': True, 'quote': 'USDT', 'settle': 'USDT', 'base': 'XAU', 'info': {'instCategory': '1'}}
        stable = {'swap': True, 'quote': 'USDT', 'settle': 'USDT', 'base': 'USDC', 'info': {'instCategory': '1'}}
        usdc_settled = {'swap': True, 'quote': 'USDT', 'settle': 'USDC', 'base': 'ZEC', 'info': {'instCategory': '1'}}
        self.assertTrue(server.is_crypto_usdt_swap(crypto))
        self.assertFalse(server.is_crypto_usdt_swap(stock))
        self.assertFalse(server.is_crypto_usdt_swap(gold))
        self.assertFalse(server.is_crypto_usdt_swap(stable))
        self.assertFalse(server.is_crypto_usdt_swap(usdc_settled))

    def test_strategy_category_permission_returns_flat_tuple(self):
        allowed, reason = strategy_category_permission('SqueezeHunter', 'Squeeze Watch')
        self.assertTrue(allowed)
        self.assertEqual(reason, '')

        allowed, reason = strategy_category_permission('SqueezeHunter', 'High Volume')
        self.assertFalse(allowed)
        self.assertIsInstance(reason, str)

    def test_scan_universe_builds_top_usdt_swaps_by_volume(self):
        tickers = [
            {'symbol': 'LOW/USDT:USDT', 'quoteVolume': 10, 'percentage': 0, 'high': 1.1, 'low': 1.0},
            {'symbol': 'BTC/USDT:USDT', 'quoteVolume': 500, 'percentage': 1, 'high': 2.0, 'low': 1.9},
            {'symbol': 'HOT/USDT:USDT', 'quoteVolume': 300, 'percentage': 8, 'high': 1.3, 'low': 1.0},
        ]
        symbols, categories = _build_scan_universe_from_tickers(tickers, {}, limit=2)
        self.assertEqual(symbols, ['BTC/USDT:USDT', 'HOT/USDT:USDT'])
        self.assertEqual(categories['BTC/USDT:USDT'], 'Majors')
        self.assertEqual(categories['HOT/USDT:USDT'], 'Alpha Rel. Strength')

    def test_symbol_reservation_blocks_cross_mode_race(self):
        old_active = list(server.active_trades)
        old_reserved = set(server.reserved_symbols)
        try:
            server.active_trades = []
            server.reserved_symbols.clear()
            first, key = server.reserve_symbol_for_entry('BTCUSDT')
            second, reason = server.reserve_symbol_for_entry('BTC/USDT:USDT')
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertIn('executing', reason)
            server.release_symbol_reservation(key)
            third, key = server.reserve_symbol_for_entry('BTC-USDT-SWAP')
            self.assertTrue(third)
            server.release_symbol_reservation(key)
        finally:
            server.active_trades = old_active
            server.reserved_symbols.clear()
            server.reserved_symbols.update(old_reserved)

    def test_stale_missing_position_does_not_block_new_entries(self):
        old_active = list(server.active_trades)
        old_reserved = set(server.reserved_symbols)
        try:
            server.active_trades = [{
                'status': 'active',
                'symbol': 'NOTUSDT',
                'direction': 'long',
                'protection_status': 'failed',
                'sync_status': 'awaiting exact OKX close lifecycle',
                'sl': 0,
                'tp1': 0,
            }]
            server.reserved_symbols.clear()
            blocked = active_unprotected_trades()
            self.assertEqual(blocked, [])
            reserved, key = server.reserve_symbol_for_entry('NOT-USDT-SWAP')
            self.assertTrue(reserved, key)
            server.release_symbol_reservation(key)
        finally:
            server.active_trades = old_active
            server.reserved_symbols.clear()
            server.reserved_symbols.update(old_reserved)

    def test_confirmed_without_exchange_verification_is_not_protected(self):
        old_active = list(server.active_trades)
        try:
            trade = {
                'status': 'active',
                'symbol': 'BTCUSDT',
                'direction': 'long',
                'protection_status': 'confirmed',
                'sl': 99.0,
                'tp1': 101.0,
                'exchange_protection_verified': False,
            }
            server.active_trades = [dict(trade)]
            self.assertFalse(has_valid_protection(trade))
            self.assertEqual(len(active_unprotected_trades()), 1)
            trade['exchange_protection_verified'] = True
            server.active_trades = [dict(trade)]
            self.assertTrue(has_valid_protection(trade))
            self.assertEqual(active_unprotected_trades(), [])
        finally:
            server.active_trades = old_active

    def test_live_snapshot_does_not_copy_unverified_local_tpsl(self):
        tracked = [{
            'status': 'active',
            'symbol': 'BTCUSDT',
            'instId': 'BTC-USDT-SWAP',
            'direction': 'long',
            'strategy': 'MacroSniper',
            'protection_status': 'confirmed',
            'sl': 99.0,
            'tp1': 101.0,
            'exchange_protection_verified': False,
        }]
        live_positions = [{
            'symbol': 'BTCUSDT',
            'instId': 'BTC-USDT-SWAP',
            'direction': 'long',
            'side': 'long',
            'entry': 100.0,
            'entryPrice': 100.0,
            'markPrice': 100.5,
            'contracts': 1.0,
            'info': {'instId': 'BTC-USDT-SWAP'},
        }]
        rows = build_live_trade_snapshot(
            tracked_records=tracked,
            live_positions=live_positions,
            include_potentials=False,
        )
        self.assertEqual(rows[0]['protection_status'], 'unconfirmed')
        self.assertNotEqual(rows[0].get('tp1'), 101.0)
        self.assertNotEqual(rows[0].get('sl'), 99.0)

    def test_protection_verification_requires_both_tp_and_sl(self):
        self.assertFalse(_algo_has_take_profit_and_stop_loss({'tpTriggerPx': '1.2'}))
        self.assertFalse(_algo_has_take_profit_and_stop_loss({'slTriggerPx': '0.9'}))
        self.assertTrue(_algo_has_take_profit_and_stop_loss({
            'tpTriggerPx': '1.2',
            'slTriggerPx': '0.9',
        }))
        self.assertTrue(_algo_has_take_profit_and_stop_loss({
            'linkedAlgoOrd': {'tpTriggerPx': '1.2', 'slTriggerPx': '0.9'},
        }))

    def test_protection_verification_matches_algo_or_client_id(self):
        algo = {
            'algoId': 'algo-1',
            'algoClOrdId': 'client-1',
            'linkedAlgoOrd': {'algoId': 'linked-1'},
        }
        self.assertTrue(_algo_identifier_matches(algo, {'algo-1'}))
        self.assertTrue(_algo_identifier_matches(algo, {'client-1'}))
        self.assertTrue(_algo_identifier_matches(algo, {'linked-1'}))
        self.assertFalse(_algo_identifier_matches(algo, {'other'}))

    def test_protection_verification_requires_size_coverage(self):
        algos = [
            {'sz': '4', 'tpTriggerPx': '1.2', 'slTriggerPx': '0.9'},
            {'sz': '3', 'tpTriggerPx': '1.2', 'slTriggerPx': '0.9'},
        ]
        self.assertFalse(protection_algos_cover_size(algos, 10))
        self.assertTrue(protection_algos_cover_size(algos, 7))

    def test_expected_edge_rejects_fee_flip_target(self):
        quality = {'exit_slippage_pct': 0.00025}
        weak = server.expected_trade_edge(1200.0, 0.0015, quality)
        strong = server.expected_trade_edge(1200.0, 0.0080, quality)
        self.assertFalse(weak['passes'])
        self.assertTrue(strong['passes'])

    @patch.object(server, 'get_btc_market_regime', return_value='trending')
    def test_macro_sniper_uses_symbol_for_major_filter(self, _regime):
        df = sample_frame()
        allowed, reason = server.evaluate_mode_gate(
            'MacroSniper', 'bullish', 50.0,
            {'1h': 'bull', '4h': 'bull', '1d': 'bull'},
            True, 2.0, 0.5, False, False, df,
            {'state': 'steady', 'profit_factor': 1.0},
            'BTC/USDT:USDT',
        )
        self.assertTrue(allowed, reason)

    def test_performance_excludes_funding_from_learning(self):
        rows = [
            {'realizedPnl': 101.0, 'fundingFee': 100.0, 'alphaPnl': 1.0},
            {'realizedPnl': -99.0, 'fundingFee': -100.0, 'alphaPnl': 1.0},
        ]
        with patch.object(server, 'realized_strategy_rows', return_value=rows):
            perf = server.strategy_performance('Contrarian')
        self.assertEqual(perf['total_pnl'], 2.0)
        self.assertTrue(perf['funding_excluded'])

    def test_lifecycle_match_does_not_reuse_old_posid_strategy(self):
        old_journal = list(server.trade_journal)
        old_active = list(server.active_trades)
        try:
            server.active_trades = []
            server.trade_journal = [
                {
                    'posId': 'same-pos', 'instId': 'BTC-USDT-SWAP',
                    'direction': 'long', 'strategy': 'MeanReversion',
                    'opened_at': '2026-06-29T00:00:00+00:00',
                },
                {
                    'posId': 'same-pos', 'instId': 'BTC-USDT-SWAP',
                    'direction': 'long', 'strategy': 'MacroSniper',
                    'opened_at': '2026-06-30T00:00:00+00:00',
                },
            ]
            record = {
                'id': 'same-pos',
                'info': {
                    'posId': 'same-pos', 'instId': 'BTC-USDT-SWAP',
                    'direction': 'long',
                    'cTime': str(server.timestamp_ms('2026-06-30T00:00:20+00:00')),
                },
            }
            matched = server.lifecycle_trade_for_history(record)
            self.assertEqual(matched['strategy'], 'MacroSniper')
        finally:
            server.trade_journal = old_journal
            server.active_trades = old_active

    def test_lifecycle_match_prefers_closer_entry_when_posid_is_reused(self):
        old_journal = list(server.trade_journal)
        old_active = list(server.active_trades)
        try:
            server.active_trades = []
            server.trade_journal = [
                {
                    'posId': 'ETH-USDT-SWAP', 'instId': 'ETH-USDT-SWAP',
                    'direction': 'short', 'strategy': 'SqueezeHunter',
                    'entry': 1800.0, 'opened_at': '2026-06-30T00:00:00+00:00',
                },
                {
                    'posId': 'ETH-USDT-SWAP', 'instId': 'ETH-USDT-SWAP',
                    'direction': 'short', 'strategy': 'MeanReversion',
                    'entry': 1881.0, 'opened_at': '2026-06-30T00:03:00+00:00',
                },
            ]
            record = {
                'id': 'ETH-USDT-SWAP',
                'openPrice': 1880.96,
                'info': {
                    'posId': 'ETH-USDT-SWAP', 'instId': 'ETH-USDT-SWAP',
                    'direction': 'short', 'openAvgPx': '1880.96',
                    'cTime': str(server.timestamp_ms('2026-06-30T00:04:00+00:00')),
                },
            }
            matched = server.lifecycle_trade_for_history(record)
            self.assertEqual(matched['strategy'], 'MeanReversion')
        finally:
            server.trade_journal = old_journal
            server.active_trades = old_active

    def test_accounting_quarantines_loss_outside_lifecycle_envelope(self):
        lifecycle = {
            'entry': 0.809,
            'sl': 0.817,
            'original_sl_dist': 0.008,
            'direction': 'short',
            'max_planned_loss_usdt': 18.0,
        }
        record = {
            'realizedPnl': -134.10,
            'openPrice': 0.809,
            'closePrice': 1.3217,
        }
        result = server.assess_accounting_record(record, lifecycle)
        self.assertEqual(result['accounting_status'], 'quarantined')
        self.assertFalse(result['eligible_for_learning'])

    def test_accounting_accepts_normal_stop_loss(self):
        lifecycle = {
            'entry': 100.0,
            'sl': 98.0,
            'original_sl_dist': 2.0,
            'direction': 'long',
            'max_planned_loss_usdt': 18.0,
        }
        record = {'realizedPnl': -12.0, 'openPrice': 100.0, 'closePrice': 97.8}
        result = server.assess_accounting_record(record, lifecycle)
        self.assertEqual(result['accounting_status'], 'verified')
        self.assertTrue(result['eligible_for_learning'])

    def test_accounting_allows_average_entry_drift_inside_risk_envelope(self):
        lifecycle = {
            'entry': 100.0,
            'sl': 98.0,
            'original_sl_dist': 2.0,
            'direction': 'long',
            'max_planned_loss_usdt': 18.0,
            'strategy': 'MeanReversion',
            'protection_status': 'confirmed',
        }
        record = {'realizedPnl': -8.0, 'openPrice': 103.5, 'closePrice': 99.2}
        result = server.assess_accounting_record(record, lifecycle)
        self.assertEqual(result['accounting_status'], 'verified')
        self.assertTrue(result['eligible_for_learning'])

    def test_linked_tp_limit_oco_resolves_to_linked_stop(self):
        algos = [{
            'instId': 'ETH-USDT-SWAP',
            'side': 'buy',
            'algoId': 'tp-parent',
            'tpOrdPx': '1600',
            'linkedAlgoOrd': {'algoId': 'linked-sl', 'slTriggerPx': '1620', 'tpTriggerPx': '1588', 'tpOrdPx': '1588'},
        }]
        result = server.protective_algo_targets(
            algos, 'ETH-USDT-SWAP', 'buy', {'tp-parent'}
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['algoId'], 'linked-sl')
        self.assertTrue(result[0]['tp_limit_linked'])
        self.assertEqual(result[0]['tpTriggerPx'], '1588')

    def test_algo_amend_checks_item_level_error(self):
        failed, code, message = server.okx_algo_amend_error({
            'code': '0',
            'data': [{'sCode': '51098', 'sMsg': 'invalid linked TP/SL amend'}],
        })
        self.assertTrue(failed)
        self.assertEqual(code, '51098')
        self.assertIn('linked', message)

    def test_amend_linked_stop_never_sends_tp_fields(self):
        algo = {
            'instId': 'ETH-USDT-SWAP',
            'algoId': 'linked-sl',
            'tp_limit_linked': True,
        }
        response = {'code': '0', 'data': [{'sCode': '0', 'sMsg': ''}]}
        with patch.object(server.okx, 'private_post_trade_amend_algos', return_value=response) as amend:
            _, failed, _, _ = server.amend_protective_stop(
                algo,
                '1590',
                {'newTpTriggerPx': '1500', 'newTpOrdPx': '-1'},
            )
        self.assertFalse(failed)
        payload = amend.call_args.args[0]
        self.assertNotIn('newTpTriggerPx', payload)
        self.assertEqual(payload['newSlTriggerPx'], '1590')

    def test_amend_retries_stop_only_after_51098(self):
        rejected = {
            'code': '1',
            'data': [{'sCode': '51098', 'sMsg': 'linked TP limit conflict'}],
        }
        accepted = {'code': '0', 'data': [{'sCode': '0', 'sMsg': ''}]}
        algo = {'instId': 'ETH-USDT-SWAP', 'algoId': 'oco', 'tp_limit_linked': False}
        with patch.object(
            server.okx,
            'private_post_trade_amend_algos',
            side_effect=[rejected, accepted],
        ) as amend:
            _, failed, _, _ = server.amend_protective_stop(
                algo,
                '1590',
                {'newTpTriggerPx': '1500', 'newTpOrdPx': '-1'},
            )
        self.assertFalse(failed)
        self.assertEqual(amend.call_count, 2)
        self.assertIn('newTpTriggerPx', amend.call_args_list[0].args[0])
        self.assertNotIn('newTpTriggerPx', amend.call_args_list[1].args[0])


if __name__ == '__main__':
    unittest.main()
