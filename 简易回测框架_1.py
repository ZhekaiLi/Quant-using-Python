import pandas as pd
import tushare as ts
import dateutil
import datetime
import matplotlib.pyplot as plt

ts.set_token('1b70493d3849bac8c98d5374657cf9750e1c3806d479ced9e9f14826')
pro = ts.pro_api()

# 获得截止到现在，所有交易日的日期
address = "trade_cals/trade_cal_" + str(datetime.date.today()) + ".csv"
try:
    trade_cal = pd.read_csv(address, dtype=str)
except FileNotFoundError:
    pro.trade_cal().to_csv(address)
    trade_cal = pd.read_csv(address, dtype=str)


class Context:
    def __init__(self, cash, start_date, end_date):
        self.cash = cash
        self.start_date = start_date
        self.end_date = end_date
        self.positions = {}
        self.benchmark = None
        self.date_range = trade_cal[(trade_cal['is_open'] == '1') & \
                                    (trade_cal['cal_date'] >= start_date) & \
                                    (trade_cal['cal_date'] <= end_date)]['cal_date'].values
        self.dt = start_date


class G:
    """存储并标明全局变量
    创建对象g=G()后，使用 g.变量名=值 的方式来存储全局变量
    """
    pass


# 只支持一只股票作为基准
def set_benchmark(security):
    context.benchmark = security


# 获取前count天的股票数据
def attribute_history(security, count, fields=('open', 'close', 'high', 'low', 'volume')):
    end_date = (dateutil.parser.parse(context.dt) - datetime.timedelta(days=1)).strftime('%Y%m%d')
    start_date = trade_cal[(trade_cal['is_open'] == '1') & (trade_cal['cal_date'] <= end_date)].iloc[-count, 2]
    return attribute_daterange_history(security, start_date, end_date, fields)


def attribute_daterange_history(security, start_date, end_date, fields=('open','close','high','low','volume')):
    address = 'securities/' + security + '_' + start_date + '_' + end_date + '.csv'
    try:
        df = pd.read_csv(address, index_col='trade_date', parse_dates=['trade_date']).loc[start_date:end_date, :]
    except FileNotFoundError:
        df = pro.daily(ts_code=security, start_date=start_date, end_date=end_date)
        df.to_csv(address)
        df = pd.read_csv(address, index_col='trade_date', parse_dates=['trade_date']).loc[start_date:end_date, :]
    df = df.sort_index() # 升序排列日期，使得表格由上到下日期递增
    return df


def get_today_data(security):
    try:
        data = g.hist.loc[dateutil.parser.parse(context.dt), :]
    except KeyError:
        data = pd.Series(dtype=float)
    return data


def _order(today_data, security, amount):
    if today_data.empty:
        print("当前股票今日停牌")
        return
    # 获取股票价格
    price = today_data['open']

    # 判断是否持有该股票
    try:
        test = context.positions[security]
    except KeyError:
        # 如果卖出操作，直接退出函数
        if amount <= 0:
            print("未持有改股票")
            return
        # 如果买入操作，创建position
        context.positions[security] = pd.Series(dtype=float)
        context.positions[security]['amount'] = 0

    # 卖出股票的数量不能超过持仓
    if context.positions[security].get('amount') < -amount:
        amount = -context.positions[security].amount
        print("卖出股票不能超过持仓，已调整为全仓")
    # 买入股票的价格不能超过现金
    if context.cash - amount*price < 0:
        amount = int(context.cash/price)
        print("现金不够，已调整为%d" % (amount))
    # 买入/卖出操作时，必须以100的倍数购买
    if amount % 100 != 0:
        # 除非全部卖出
        if amount != -context.positions[security].amount:
            amount = int(amount/100) * 100
            print("无法以非100的倍数购买，已调整为%d" % (amount))

    if amount > 0:
        print("购买了%d股" % (amount))
    else:
        print("卖出了%d股" % (-amount))

    # 更新持仓
    context.positions[security].amount = context.positions[security].get('amount') + amount
    if context.positions[security].amount == 0: # 如果持仓股数为0，删除
        del context.positions[security]
    # 更新现金
    context.cash -= amount * price


def order(security, amount):
    today_data = get_today_data(security)
    _order(today_data, security, amount)


def order_target(security, amount):
    if amount < 0:
        amount = 0
        print("目标数量不能为负，已调整为0")
    today_data = get_today_data(security)
    try:
        hold_amount = context.positions[security].amount
    except KeyError:
        hold_amount = 0
    delta_amount = amount - hold_amount
    _order(today_data, security, delta_amount)


def order_value(security, value):
    today_data = get_today_data(security)
    if today_data.empty:
        return
    amount = int(value / today_data['open'])
    _order(today_data, security, amount)


def order_target_value(security, value):
    if value < 0:
        value = 0
        print("价值不能为负，已调整为0")
    today_data = get_today_data(security)
    try:
        hold_value = context.positions[security].amount * today_data['open']
    except KeyError:
        hold_value = 0
    delta_value = value - hold_value
    amount = int(delta_value / today_data['open'])
    _order(today_data, security, amount)


# 回测函数
def run():
    initialize(context)

    plt_df = pd.DataFrame(index=pd.to_datetime(context.date_range), columns=['value'])
    last_prices = {}
    initial_value = context.cash
    for dt in context.date_range:
        context.dt = dt
        handle_data(context)
        value = context.cash
        for stock in context.positions.keys():
            try:
                data = get_today_data(stock)
                price = data['open']
                last_prices[stock] = price
            except KeyError:
                # 如果取不到，说明当日停牌，取之前未停牌时的价格
                price = last_prices[stock]
            value += price * context.positions[stock].amount
        plt_df.loc[dt, 'value'] = value
    plt_df['ratio'] = (plt_df['value'] - initial_value) / initial_value

    bm_df = attribute_daterange_history(context.benchmark, context.start_date, context.end_date)
    bm_init = bm_df['open'][0]
    plt_df['benchmark_ratio'] = (bm_df['open'] - bm_init) / bm_init

    plt_df[['ratio', 'benchmark_ratio']].plot()
    plt.show()


def initialize(context):
    set_benchmark('601318.SH')
    g.p1 = 5
    g.p2 = 60
    g.security = '601318.SH'

    hist_1 = attribute_history(g.security, g.p2)
    hist_2 = attribute_daterange_history(g.security, context.start_date, context.end_date)
    g.hist = hist_1.append(hist_2)


def handle_data(context):
    hist = g.hist[:dateutil.parser.parse(context.dt)][-g.p2:]
    ma5 = hist['close'][-g.p1:].mean()
    ma60 = hist['close'].mean()

    if ma5 > ma60 and g.security not in context.positions.keys():
        order_value(g.security, context.cash)
    elif ma5 < ma60 and g.security in context.positions.keys():
        order_target(g.security, 0)


g = G()
context = Context(100000, '20200510', '20210101')
run()


