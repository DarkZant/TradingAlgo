import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import datetime as dt
from email.message import EmailMessage
import ssl
import smtplib
import os


def out(text):
    output.write(text + '\n')
    print(text)
    global emailbody
    emailbody += text + '\n'


def getSumFundingFees(starttime):
    fundingfees = 0
    for transaction in client.futures_income_history(incomeType='FUNDING_FEE', startTime=starttime, limit=1000):
        fundingfees += float(transaction['income'])
    return fundingfees


def getTotalTransactions(ttype):
    total = 0
    servertime = client.get_server_time()['serverTime']
    starttime = servertime - 64281600000
    for transaction in client.futures_income_history(incomeType=ttype, startTime=starttime, limit=1000):
        total += float(transaction['income'])
    return round(total, 8)


def getFuturesAccountBalance():
    balance = 0
    bnbvol = 0
    bnbcut = 0.945
    for coin in client.futures_account_balance():
        if coin['asset'] == 'USDT' or coin['asset'] == 'BUSD':
            balance += float(coin['balance'])
            out(f'Added {coin["balance"]} {coin["asset"]}')
        elif coin['asset'] == 'BNB':
            bnbbal = float(coin["balance"]) * bnbcut
            if bnbbal > 0:
                bnbprice = float(client.futures_ticker(symbol='BNBUSDT')['lastPrice'])
            else:
                bnbprice = 0
            bnbvol = round(bnbbal * bnbprice, 8)
            balance += bnbvol
            out(f'Added {bnbvol} USD ({bnbbal} BNB * {bnbprice} USD and volume has been cut by {bnbcut})')
    out(f'Total balance is {round(balance, 3)} USD stablecoin')
    if bnbvol <= bnbAlert * balance:
        out(f'BNB BALANCE IS LOW: {round(bnbvol / balance * 100, 2)} % of account')
    return balance

class Trade:
    coinpair = ''
    tradeSide = False
    volume = 0
    tpId = 0
    slId = 0
    tradeIsExecuted = False
    canTrade = False

    entryId = 0
    coinpairInfo = {}
    tradeResult = ""

    MINUSDVOL = 5.25

    def __init__(self, coinpair):
        self.coinpair = coinpair

    def __repr__(self):
        return f'{self.coinpair},{self.tradeSide},{self.volume},{self.tpId},{self.slId},{self.tradeIsExecuted},' \
               f'{self.canTrade}'

    def __str__(self):
        return f'{self.coinpair},{self.tradeSide},{self.volume},{self.tpId},{self.slId},{self.tradeIsExecuted},' \
               f'{self.canTrade}'

    def getPrice(self, rawPrice, multiplier):
        if self.coinpairInfo != {}:
            precision = self.coinpairInfo['pricePrecision']
        else:
            precision = 8
        price = float(rawPrice * multiplier)
        price = round(price, precision)
        return price

    def getMinVolume(self, price):
        if self.coinpairInfo != {}:
            precision = self.coinpairInfo['quantityPrecision']
        else:
            precision = 8
        vol = float(self.MINUSDVOL / price)
        vol = round(vol, precision)
        while vol * price <= self.MINUSDVOL:
            vol = round(vol + 1 / 10**precision, precision)
        return vol

    def getVolume(self, price):
        stablecoinvol = bal * percentPerTrade
        if self.coinpairInfo != {}:
            precision = self.coinpairInfo['quantityPrecision']
        else:
            precision = 8
        vol = float(stablecoinvol * leverage / price)
        vol = round(vol, precision)
        while vol * price <= self.MINUSDVOL:
            vol = round(vol + 1 / 10**precision, precision)
        return vol

    def trade(self):
        price = float(client.futures_ticker(symbol=self.coinpair)['lastPrice'])
        self.volume = self.getVolume(price)
        if self.tradeSide:
            openingSide = client.SIDE_BUY
            closingSide = client.SIDE_SELL
            activationPrice = self.getPrice(price, longTPActiv)
            sl = self.getPrice(price, longSL)
        else:
            openingSide = client.SIDE_SELL
            closingSide = client.SIDE_BUY
            activationPrice = self.getPrice(price, shortTPActiv)
            sl = self.getPrice(price, shortSL)
        noExceptions = True

        try:
            client.futures_change_leverage(symbol=self.coinpair, leverage=leverage)
        except BinanceAPIException as e:
            out(f'{self.coinpair}: Exception raised while changing leverage: {e}')
            errorCode = str(e)[15:19]
            if errorCode == '4028':
                try:
                    for symbol in client.futures_leverage_bracket():
                        if symbol['symbol'] == self.coinpair:
                            newLev = symbol['brackets'][0]['initialLeverage']
                            out(f'Changing leverage to {newLev}')
                            client.futures_change_leverage(symbol=self.coinpair, leverage=newLev)
                            break
                except BinanceAPIException as e:
                    out(f'{self.coinpair}: Exception raised while rechanging leverage: {e}')
                    noExceptions = False
            else:
                noExceptions = False

        if noExceptions:
            try:
                self.slId = client.futures_create_order(symbol=self.coinpair, side=closingSide, reduceOnly="true",
                type=client.FUTURE_ORDER_TYPE_STOP_MARKET, stopPrice=sl, quantity=self.volume)['orderId']
            except BinanceAPIException as e:
                out(f'{self.coinpair}: Exception raised with stoploss order: {e}')
                noExceptions = False

            try:
                self.tpId = client.futures_create_order(symbol=self.coinpair, side=closingSide, reduceOnly="true",
                type="TRAILING_STOP_MARKET", callbackRate=callbackRate, activationPrice=activationPrice,
                                                        quantity=self.volume)['orderId']
            except BinanceAPIException as e:
                out(f'{self.coinpair}: Exception raised with takeprofit order: {e}')
                noExceptions = False

        if noExceptions:
            errorCode = '0'
            while errorCode == '0' or errorCode == '1001':
                try:
                    self.entryId = client.futures_create_order(symbol=self.coinpair, side=openingSide,
                    type=client.FUTURE_ORDER_TYPE_MARKET, quantity=self.volume)['orderId']
                    out(f'{openingSide} {self.volume} {self.coinpair + ".P"} at {price} USD '
                        f'({round(self.volume * price,2)} USD Total); SL at {sl}; TP Activation at {activationPrice}')
                    self.tradeIsExecuted = True
                    errorCode = ''
                except BinanceAPIException as e:
                    out(f'{self.coinpair}: Exception raised with main short order: {e}')
                    errorCode = str(e)[15:19]

        else:
            out(f'{self.coinpair}: No opening order sent because exception was raised')
        out('-' * 5)

    def endTrade(self):
        noExceptions = True
        try:
            client.futures_cancel_order(symbol=self.coinpair, orderId=self.slId)
        except BinanceAPIException as e:
            out(f"{self.coinpair}: SL was hit or inexistent: {e}")
            noExceptions = False
            self.tradeResult = "SL"

        try:
            client.futures_cancel_order(symbol=self.coinpair, orderId=self.tpId)
        except BinanceAPIException as e:
            out(f"{self.coinpair}: TP was hit or not inexistent: {e}")
            noExceptions = False
            if self.tradeResult != "":
                self.tradeResult = "BOTH"
            else:
                self.tradeResult = "TP"

        if noExceptions and self.tradeIsExecuted:
            if self.tradeSide:
                closingSide = client.SIDE_SELL
            else:
                closingSide = client.SIDE_BUY
            try:
                client.futures_create_order(symbol=self.coinpair, side=closingSide,
                                            type=client.FUTURE_ORDER_TYPE_MARKET,
                                            quantity=self.volume, reduceOnly="true")
                self.tradeResult = "CLOSE"
            except BinanceAPIException as e:
                out(f"{self.coinpair}: Couldn't send closing order: {e}")
            else:
                out(f"{self.coinpair}: Canceled stoploss + takeprofit and sent closing order")
        else:
            out(f"{self.coinpair}: No closing order sent because exception was raised")

        out(f'{self.coinpair}: End of trade' + endSection)

    def documentTrade(self):
        if self.tradeIsExecuted:
            try:
                self.writeTradeResults()
            except Exception as e:
                out(f"{self.coinpair}: Exception raised while writing trade results: {e}")
        try:
            self.writeTradeData()
        except Exception as e:
            out(f"{self.coinpair}: Exception raised while writing trade data: {e}")

    def writeTradeResults(self):
        serverTime = client.get_server_time()['serverTime']
        tradeTime = serverTime - timetowait * 1000 - 180000
        recentTrades = client.futures_account_trades(symbol=self.coinpair, startTime=tradeTime)

        avgEntryPrice = 0
        avgClosingPrice = 0
        pnl = 0
        fees = 0
        closingTime = 0
        closingDone = False
        closingStarted = False
        if self.tradeSide:
            closingSide = 'SELL'
        else:
            closingSide = 'BUY'

        for toDocument in reversed(recentTrades):
            tradepnl = float(toDocument['realizedPnl'])
            quantity = float(toDocument['qty'])

            if toDocument['side'] == closingSide and tradepnl != 0:
                if closingDone:
                    break
                if not closingStarted:
                    closingStarted = True
                avgClosingPrice += quantity / self.volume * float(toDocument["price"])
                pnl += tradepnl
                if closingTime == 0:
                    closingTime = toDocument['time'] / 1000
                if toDocument['commissionAsset'] == 'BNB':
                    fees += float(toDocument['commission']) * bnbPrice
                else:
                    fees += float(toDocument['commission'])

            elif toDocument['side'] != closingSide and closingStarted:
                if tradepnl != 0:
                    break
                if not closingDone:
                    closingDone = True
                avgEntryPrice += quantity / self.volume * float(toDocument["price"])
                if toDocument['commissionAsset'] == 'BNB':
                    fees += float(toDocument['commission']) * bnbPrice
                else:
                    fees += float(toDocument['commission'])

        if pnl == 0:
            estimatePrice = float(recentTrades[0]['price'])
            fees = self.volume * estimatePrice * 0.0008
            avgEntryPrice = estimatePrice
            avgClosingPrice = estimatePrice
            closingTime = time.time()

        tradeslogs = open('TradeResults.csv', 'a')
        strdt = str(dt.datetime.fromtimestamp(time.time() - timetowait))
        dateandtime = strdt[:13] + ":00:00"
        closingTimestr = str(dt.datetime.fromtimestamp(closingTime))[:19]
        tradestr = [dateandtime, self.coinpair + '.P', str(avgEntryPrice), str(avgClosingPrice), str(round(pnl, 5)),
                    str(round(pnl - fees, 5)), self.tradeResult, closingTimestr]
        tradeslogs.write(','.join(tradestr) + '\n')
        tradeslogs.close()

    def writeTradeData(self):
        strdt = str(dt.datetime.fromtimestamp(time.time() - timetowait))
        dateandtime = strdt[:13] + ":00:00"
        klines = getCompletedKlines(self.coinpair, MALength + 1, tf)
        prevKline = klines[-2]
        tradeKline = klines[-1]
        smallerKlines = getCompletedKlines(self.coinpair, 2, Client.KLINE_INTERVAL_30MINUTE)
        movingAverage = str(getMovingAverage(klines[:-1]))
        btcklines = getCompletedKlines('BTCUSDT', MALength + 1, tf)
        btcMABiggerClose = float(btcklines[-2][4]) > getMovingAverage(btcklines[:-1])
        atr = getATR(klines[-(ATRLength + 2):-1])
        coinstring = [dateandtime, self.coinpair + ".P", prevKline[1], prevKline[2], prevKline[3], prevKline[4],
                      prevKline[5], movingAverage, str(btcMABiggerClose), str(atr), tradeKline[1], tradeKline[2],
                      tradeKline[3], tradeKline[4], tradeKline[5], smallerKlines[0][2], smallerKlines[0][3],
                      smallerKlines[0][4], smallerKlines[1][1], smallerKlines[1][2], smallerKlines[1][3]]
        tradeData = open("TradeData.csv", 'a')
        tradeData.write(','.join(coinstring) + '\n')
        tradeData.close()

    def setCoinpairInfo(self, exchangeCoinpairsInfos):
        for symbol in exchangeCoinpairsInfos:
            if symbol['symbol'] == self.coinpair:
                self.coinpairInfo = symbol
                return


def getCompletedKlines(coinpair, amount, timef):
    klines = client.futures_klines(symbol=coinpair, interval=timef, limit=amount + 1)
    timeWindow = time.time() - 600
    i = 0
    while klines[-1][0] / 1000 < timeWindow and i < 20:
        out(f'{coinpair}: Waiting for kline...')
        time.sleep(0.5)
        klines = client.futures_klines(symbol=coinpair, interval=timef, limit=amount + 1)
        i += 1
    return klines[:-1]


def getUncompletedKline(coinpair, timef):
    klines = client.futures_klines(symbol=coinpair, interval=timef, limit=1)
    timeWindow = time.time() - 600
    i = 0
    while klines[-1][0] / 1000 < timeWindow and i < 20:
        out(f'{coinpair}: Waiting for kline...')
        time.sleep(0.5)
        klines = client.futures_klines(symbol=coinpair, interval=timef, limit=1)
        i += 1
    return klines


def getInput():
    out(inputFile.readline().strip())
    inputValue = float(inputFile.readline().strip())
    out(str(inputValue))
    return inputValue


def getTickers():
    final = []
    tickers = client.futures_ticker()
    timeWindow = time.time() - 300
    for ticker in tickers:
        if ticker['closeTime'] / 1000 > timeWindow:
            final.append(ticker)
    return final


def getMovingAverage(klines):
    sum = 0
    for kline in klines:
        sum += float(kline[4])
    return sum / len(klines)


def getATR(klines):
    array = []
    for i in range(1, len(klines)):
        DR = float(klines[i][2]) - float(klines[i][3])
        HC = abs(float(klines[i][2]) - float(klines[i - 1][4]))
        LC = abs(float(klines[i][3]) - float(klines[i - 1][4]))
        array.append(max(DR, HC, LC))
    return sum(array) / len(array)


def verifyTradeCondition(var):
    return var >= 3 or var <= -3


if __name__ == '__main__':
    endTF = '\n' + '*' * 30
    endSection = '\n' + '-' * 5
    startDt = str(dt.datetime.now())
    outputname = startDt[:10] + "_" + startDt[11:13] + ";" + startDt[14:16] + ";" + startDt[17:19]
    output = open(f'Logs/{outputname}.txt', 'w')
    emailbody = ''
    testnet = False
    if testnet:  # FIXME Enter your own API information
        client = Client(api_key='YOUR_BINANCE_FUTURES_TESTNET_API_KEY',
                        api_secret='YOUR_BINANCE_FUTURES_TESTNET_API_SECRET', testnet=True)
    else:
        client = Client(api_key='YOUR_BINANCE_FUTURES_API_KEY',
                        api_secret='YOUR_BINANCE_FUTURES_API_SECRET')

    tf = Client.KLINE_INTERVAL_1HOUR
    timetowait = 1 * 60 * 60  # hours * mins * seconds
    bnbAlert = 1 / 100  # (%)
    serverTimeDiff = 975  # (ms)
    endOfDayHour = 20
    out('Version 1.0 \n')

    inputFile = open('Inputs.txt', 'r')
    leverage = int(getInput())
    percentPerTrade = getInput() / 100
    callbackRate = getInput()
    shortTPActiv = getInput() / 100 + 1
    shortSL = getInput() / 100 + 1
    longTPActiv = getInput() / 100 + 1
    longSL = getInput() / 100 + 1
    MALength = int(getInput())
    ATRLength = int(getInput())
    maxConcTrades = int(getInput())
    neededVar = 2
    approxNeededVar = neededVar - 0.5
    inputFile.close()
    out('')

    sender = 'YOUR_SENDING_EMAIL' # FIXME Enter your own Email information
    receiver = 'YOUR_RECEIVING_EMAIL'
    password = 'YOUR_SENDING_EMAIL_PASSWORD'
    subject = 'Crypto BOT output'
    em = EmailMessage()
    em['From'] = sender
    em['To'] = receiver
    em['Subject'] = subject
    context = ssl.create_default_context()

    timeframesPassed = 0
    nbtrades = 0
    prevBal = getFuturesAccountBalance()
    fundingfees = getTotalTransactions('FUNDING_FEE')
    pnl = getTotalTransactions('REALIZED_PNL')
    ratio = round((-fundingfees / (-fundingfees + pnl) * 100), 2)
    out(f'Funding fees: {fundingfees} USD; PnL: {pnl} USD; % of profit taken by funding fees: {ratio}%')

    coinsPrice = {}
    symbols = []
    for coinpair in getTickers():
        symbol = coinpair['symbol']
        price = float(coinpair['lastPrice'])
        coin = symbol[:-4]
        if symbol[-4:] == 'USDT' or symbol[-4:] == 'BUSD':
            if not (coin in symbols):
                symbols.append(coin)
                try:
                    busd = client.futures_ticker(symbol=coin + "BUSD", interval='1h', limit=1)
                    timeWindow = time.time() - 300
                    busdExists = busd['closeTime'] / 1000 > timeWindow
                except Exception as e:
                    busdExists = False
                if busdExists:
                    coinsPrice[coin + 'BUSD'] = price
                else:
                    coinsPrice[symbol] = price

    trades = []
    initialtrades = open('Trades.csv', 'r')
    tlines = open('Trades.csv', 'r')
    nblignes = len(tlines.readlines())
    tlines.close()
    out(f'\n{nblignes} initial trades:')
    for i in range(nblignes):
        tradeArray = initialtrades.readline().strip().split(',')
        trade = Trade(tradeArray[0])
        trade.tradeSide = eval(tradeArray[1])
        trade.volume = float(tradeArray[2])
        trade.tpId = int(tradeArray[3])
        trade.slId = int(tradeArray[4])
        trade.tradeIsExecuted = eval(tradeArray[5])
        trade.canTrade = eval(tradeArray[6])
        trades.append(trade)
    for toPrint in trades:
        out(f'{toPrint}')
    initialtrades.close()

    out(f'\nWaiting for timeframe...\nApprox. wait time: {round((timetowait - (time.time() % timetowait)) / 3600, 1)} '
        f'hours' + endTF)
    output.close()

    time.sleep(timetowait - (time.time() % timetowait))
    while True:
        output = open(f'Logs/{outputname}.txt', 'a')
        earlyDt = str(dt.datetime.now())
        currentHour = int(earlyDt[11:13])
        currentMinute = int(earlyDt[14:16])
        if currentMinute == 59:
            currentHour += 1
        isEndofDay = currentHour == endOfDayHour

        starttime = time.time()
        timeframesPassed += 1
        out(f'{dt.datetime.now()}')
        try:
            timeDiff = abs(float(client.futures_time()['serverTime'] - time.time() * 1000))
            while timeDiff >= serverTimeDiff:
                out(f'Time difference with server is bigger than {serverTimeDiff}ms: {timeDiff}')
                os.system('w32tm/resync')
                timeDiff = abs(float(client.futures_time()['serverTime'] - time.time() * 1000))
            out(f'Time difference with server is {round(timeDiff, 1)}ms' + endSection)
        except Exception as e:
            out(f"Exception while checking time: {e}")
            servertime = 0

        newPrices = []
        try:
            newPrices = getTickers()
        except Exception as e:
            out("Exception while getting new prices: " + str(e))

        tradesThatCanTrade = 0
        for toCount in trades:
            if toCount.canTrade:
                tradesThatCanTrade += 1

        if tradesThatCanTrade <= maxConcTrades:
            for toManage in trades:
                if toManage.canTrade:
                    toManage.endTrade()

        tradesToDocument = trades.copy()
        trades.clear()

        try:
            i = 0
            while i < 20:
                accountInfo = client.futures_account()
                unrPNL = float(accountInfo['totalUnrealizedProfit'])
                if unrPNL == 0:
                    break
                else:
                    out("Waiting for account balance update...")
                    time.sleep(0.5)
                i += 1
        except Exception as e:
            out(f"Exception while waiting for account update: {e}")

        try:
            bal = getFuturesAccountBalance()
            pnl = round(bal - prevBal, 3)
            out(f'Account % change during {tf} is {round((bal - prevBal) / prevBal * 100, 3)}% or {pnl} USD')
            fundingfees = getSumFundingFees(int(time.time() * 1000) - timetowait * 1000)
            if fundingfees != 0:
                ratioFF = round((-fundingfees / (-fundingfees + pnl) * 100), 2)
                out(f'Funding fees for {tf} were {fundingfees} USD which is {ratioFF}% of PNL' + endSection)
            else:
                out('-----')
            prevBal = bal

            balcsv = open('Balance.csv', 'a')
            strDandT = str(dt.datetime.fromtimestamp(time.time()))
            dandT = strDandT[:13] + ":00:00"
            balcsv.write(f'{dandT},{bal}\n')
            balcsv.close()
        except Exception as e:
            out(f"Exception while getting account balance: {e}")

        try:
            for coinpair in newPrices:
                symbol = coinpair['symbol']
                coin = symbol[:-4]
                price = float(coinpair['lastPrice'])

                if symbol in coinsPrice:
                    lastprice = coinsPrice[symbol]
                    var = round((price - lastprice) / lastprice * 100, 2)

                    if (var >= approxNeededVar) or (var <= -approxNeededVar):
                        lastKlines = getCompletedKlines(symbol, MALength, tf)
                        lastOpen = float(lastKlines[-1][1])
                        lastClose = float(lastKlines[-1][4])
                        movingAverage = getMovingAverage(lastKlines)
                        realVar = round((lastClose - lastOpen) / lastOpen * 100, 2)

                        if realVar >= neededVar:
                            newTrade = Trade(symbol)
                            newTrade.tradeSide = True
                            newTrade.canTrade = realVar >= 3 and lastClose >= movingAverage
                            trades.append(newTrade)

                        elif realVar <= -neededVar:
                            newTrade = Trade(symbol)
                            newTrade.tradeSide = False
                            newTrade.canTrade = realVar <= -3 and lastClose < movingAverage
                            trades.append(newTrade)

                    coinsPrice[symbol] = price
                elif (not ((coin + "BUSD") in coinsPrice)) and (symbol[-4:] == 'USDT' or symbol[-4:] == 'BUSD'):
                    try:
                        busd = client.futures_ticker(symbol=coin + "BUSD", interval='1h', limit=1)
                        timeWindow = time.time() - 300
                        busdExists = busd['closeTime'] / 1000 > timeWindow
                    except Exception as e:
                        busdExists = False
                    if busdExists:
                        coinsPrice[coin + 'BUSD'] = price
                    else:
                        coinsPrice[symbol] = price
        except Exception as e:
            out("Exception while fetching coin data: " + str(e))

        try:
            out('-' * 5)
            exchangeSymbols = []
            tradesout = open('Trades.csv', 'w')

            tradesThatCanTrade = 0
            for toCount in trades:
                if toCount.canTrade:
                    tradesThatCanTrade += 1

            if tradesThatCanTrade <= maxConcTrades:
                for toTrade in trades:
                    if toTrade.canTrade:
                        if not exchangeSymbols:
                            exchangeSymbols = client.futures_exchange_info()['symbols']
                        toTrade.setCoinpairInfo(exchangeSymbols)
                        toTrade.trade()
                    tradesout.write(str(toTrade) + '\n')
                    if toTrade.tradeIsExecuted:
                        nbtrades += 1
            else:
                out(f"Too many concurrent trades ({tradesThatCanTrade}); Not trading")
                for toTrade in trades:
                    tradesout.write(str(toTrade) + '\n')
            tradesout.close()
        except Exception as e:
            out(f"Exception while opening trades: {e}")

        out(f'{round(time.time() - starttime, 2)} seconds of runtime; {timeframesPassed} * {tf} timeframes have passed;'
            f' {nbtrades} trades have been executed')

        bnbklines = getCompletedKlines('BNBUSDT', 1, tf)
        bnbPrice = (float(bnbklines[0][1]) + float(bnbklines[0][2]) + float(bnbklines[0][3]) + float(
            bnbklines[0][4])) / 4
        for trade in tradesToDocument:
            trade.documentTrade()

        out('*' * 30)

        if isEndofDay:
            try:
                em.set_content(emailbody)
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
                    smtp.login(sender, password)
                    smtp.sendmail(sender, receiver, em.as_string())
            except Exception as e:
                out(f"Exception while sending email: {e}")
        emailbody = ''

        output.close()

        time.sleep(timetowait - (time.time() % timetowait))
