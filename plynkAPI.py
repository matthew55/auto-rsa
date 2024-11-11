import asyncio
import os
import traceback

from dotenv import load_dotenv
from plynk_api import Plynk

from helperAPI import (
    Brokerage,
    getOTPCodeDiscord,
    maskString,
    printAndDiscord,
    printHoldings,
    stockOrder
)


def plynk_init(PLYNK_EXTERNAL=None, botObj=None, loop=None):
    # Initialize .env file
    load_dotenv()
    # Import Plynk account
    plynk_obj = Brokerage("Plynk")
    if not os.getenv("PLYNK") and PLYNK_EXTERNAL is None:
        print("Plynk not found, skipping...")
        return None
    plynk_creds = (
        os.environ["PLYNK"].strip().split(",")
        if PLYNK_EXTERNAL is None
        else PLYNK_EXTERNAL.strip().split(",")
    )

    # This is used by Plynk API get the OTP when needed
    def get_otp():
        if botObj is not None and loop is not None:
            # Sometimes codes take a long time to arrive
            timeout = 300  # 5 minutes
            otp_code = asyncio.run_coroutine_threadsafe(
                getOTPCodeDiscord(botObj, name, timeout=timeout, loop=loop),
                loop,
            ).result()
        else:
            otp_code = input("Please enter the OTP you received: ")
        if otp_code is None:
            raise Exception("No 2FA code found")
        return otp_code

    # Log in to Plynk account
    print("Logging in to Plynk...")
    for index, account in enumerate(plynk_creds):
        name = f"Plynk {index + 1}"
        try:
            account = account.split(":")
            plynk = Plynk(
                username=account[0],
                password=account[1],
                filename=f"{name}.pkl",
                path="./creds/"
            )
            plynk.login(otp_callback=get_otp)
            # Plynk only has one account
            plynk_obj.set_logged_in_object(name, plynk)
            account_number = plynk.get_account_number()
            plynk_obj.set_account_number(name, account_number)
            print(f"{name}: Found account {maskString(account_number)}")
            cash = plynk.get_account_total(account_number)
            plynk_obj.set_account_totals(name, account_number, cash)
        except Exception as e:
            print(f"Error logging in to Plynk: {e}")
            print(traceback.format_exc())
            continue
    print("Logged in to Plynk!")
    return plynk_obj


def plynk_holdings(plynk_obj: Brokerage, loop=None):
    for key in plynk_obj.get_account_numbers():
        for account in plynk_obj.get_account_numbers(key):
            plynk: Plynk = plynk_obj.get_logged_in_objects(key)
            try:
                # Get account holdings
                holdings = plynk.get_account_holdings(account)
                for holding in holdings:
                    symbol = holding['security']['symbol']
                    if symbol is None:
                        symbol = 'None'
                    quantity = holding['securityCount']
                    price = holding['currentValue']
                    if price is not None:
                        stock_details = plynk.get_stock_details(symbol)
                        price = stock_details['securityDetails']['lastPrice']
                    else:
                        price = 0
                    plynk_obj.set_holdings(key, account, symbol, quantity, price)
            except Exception as e:
                printAndDiscord(f"{key} {account}: Error getting holdings: {e}")
                print(traceback.format_exc())
                continue
    printHoldings(plynk_obj, loop)


def plynk_transaction(plynk_obj: Brokerage, orderObj: stockOrder, loop=None):
    print("\n==============================")
    print("Plynk Transaction Start")
    print("==============================\n")

    for s in orderObj.get_stocks():
        for key in plynk_obj.get_account_numbers():
            printAndDiscord(
                f"{key}: {orderObj.get_action()}ing {orderObj.get_amount()} of {s}...",
                loop,
            )
            for account in plynk_obj.get_account_numbers(key):
                print_account = maskString(account)
                plynk: Plynk = plynk_obj.get_logged_in_objects(key)
                try:
                    order = plynk.place_order_price(
                        account_number=account,
                        ticker=s,
                        quantity=1.0,  # $1 worth
                        side=orderObj.get_action(),
                        price="market",
                        dry_run=orderObj.get_dry()
                    )
                    # Print and send confirmation details to Discord                    
                    if order.get("success") is True or order.get("dry_run_success") is True:
                        if orderObj.get_dry():
                            printAndDiscord(
                                f"DRY RUN Success for: {key} account {print_account}: {orderObj.get_action()} {orderObj.get_amount()} shares of {s}",
                                loop,
                            )
                        else:
                            printAndDiscord(
                                f"{key} account {print_account}: {orderObj.get_action()} {orderObj.get_amount()} shares of {s}",
                                loop,
                            )
                    else:
                        print(f"Order response: {order}")
                        if 'messages' in order and order['messages'].get('messageList'):
                            for message in order['messages']['messageList']:
                                message_content = f"Message Code: {message.get('code')}, Content: {message.get('messageContent')}"
                                printAndDiscord(message_content, loop)
                except Exception as e:
                    printAndDiscord(f"{print_account}: Error placing order: {e}", loop)
                    traceback.print_exc()
                    continue
                
    print("\n==============================")
    print("Plynk Transaction End")
    print("==============================\n")

