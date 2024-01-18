# TradingAlgo
Cryptocurrency trading algorithm for Binance's USDS-M Futures.  
This algorithm follows a certain strategy with promising returns over a long period of time.  
The program runs autonomously and needs the computer to be on 24h a day (Not sleeping).  
If you provide your email information, the program will send you an email at 0:00 UTC to confirm that it is still working properly.  
Every action executed by the program is saved and documented in the different CSV files:  
* ```Logs``` : The console log for a given session.  
* ```TradeData.csv``` : Precious market data which is usually costly information.   
* ```TradeResults.csv``` : Analytics about the performance of the trading strategy.  
* ```Balance.csv``` : The progression of your account's balance, updated after every timeframe.  
* ```Trades.csv``` : The trades that the program is currently managing, nothing interesting to see there.  
* ```Inputs.txt``` : The inputs for the current strategy. Change the number under the title of the input.

## How to Install and Run
1. Download the code as a zip file and extract its contents.
2. You will need to use an IDE (I recommend [PyCharm Community Edition](https://www.jetbrains.com/pycharm/download/)) to modify and run the python code.
3. Install the [python-binance](https://python-binance.readthedocs.io/en/latest/) package and import it in your project.
4. In the ```FIXME``` sections, add your API credentials and your Email credentials.
5. You can transform the code into an executable file using [pyinstaller](https://towardsdatascience.com/convert-your-python-code-into-a-windows-application-exe-file-28aa5daf2564) or simply run it from your IDE.
6. Now, simply run your executable with administrator permissions and you're all set!
