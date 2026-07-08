import sys
sys.path.append('.')
from server_core.okx_client import okx
from server_core.utils import write_json_atomic
import server_core.config as config

print("=== 開始清空 OKX 所有持倉與委託 ===")

# 1. 撤銷所有普通掛單
try:
    open_orders = okx.fetch_open_orders()
    print(f"找到 {len(open_orders)} 個掛單")
    for order in open_orders:
        order_id = order.get('id')
        inst_id = order.get('symbol')
        print(f"撤銷普通掛單: {inst_id} (ID: {order_id})")
        okx.cancel_order(order_id, inst_id)
except Exception as e:
    print("撤銷掛單失敗:", e)

# 2. 撤銷所有策略/計畫單
for otype in ['oco', 'conditional', 'trigger', 'move_order_stop']:
    try:
        res = okx.private_get_trade_orders_algo_pending({'instType': 'SWAP', 'ordType': otype})
        if res and res.get('code') == '0':
            algos = res.get('data', [])
            print(f"找到 {len(algos)} 個策略單 ({otype})")
            for a in algos:
                algo_id = a.get('algoId')
                inst_id = a.get('instId')
                print(f"撤銷策略單: {inst_id} (ID: {algo_id})")
                okx.private_post_trade_cancel_algos([{'algoId': algo_id, 'instId': inst_id}])
    except Exception as e:
        print(f"撤銷策略單 ({otype}) 失敗:", e)

# 3. 獲取所有持倉並進行市價一鍵全平
try:
    pos_res = okx.private_get_account_positions()
    if pos_res and pos_res.get('code') == '0':
        positions = pos_res.get('data', [])
        active_positions = [p for p in positions if p.get('pos') and float(p.get('pos')) != 0]
        print(f"找到 {len(active_positions)} 個有倉位的持倉")
        for pos in active_positions:
            inst_id = pos.get('instId')
            pos_side = pos.get('posSide')
            pos_amt = pos.get('pos')
            mgn_mode = pos.get('mgnMode', 'cross')
            
            # 使用 OKX 專門的一鍵市價全平接口 (安全可靠，不受掛單影響)
            print(f"正在一鍵市價平倉: {inst_id} (方向: {pos_side}, 數量: {pos_amt})...")
            try:
                # 必須先取消該 instId 上的所有收尾/平倉委託
                orders_on_inst = okx.private_get_trade_orders_pending({'instId': inst_id})
                if orders_on_inst and orders_on_inst.get('code') == '0':
                    for o in orders_on_inst.get('data', []):
                        print(f"  [清理] 取消 inst 上的未決單: {o.get('ordId')}")
                        okx.private_post_trade_cancel_order({'instId': inst_id, 'ordId': o.get('ordId')})
                
                close_res = okx.private_post_trade_close_position({
                    'instId': inst_id,
                    'mgnMode': mgn_mode
                })
                print(f"  一鍵平倉結果: {close_res}")
            except Exception as pe:
                print(f"  平倉失敗: {pe}")
    else:
        print("獲取持倉返回錯誤:", pos_res)
except Exception as e:
    print("平倉程序出錯:", e)

# 4. 清空本地 active_trades.json 確保 UI 同步歸零
try:
    write_json_atomic(config.TRADE_FILE, [])
    print("本地 active_trades 數據已成功歸零")
except Exception as e:
    print("清空 active_trades 失敗:", e)
