"""Order mirror: turns a paper trade plan (artifacts/research/advisor_shadow/trade_plan_<v>.json) into exchange orders.

Default mode is a dry run (prints the actions, sends nothing). Bybit testnet needs BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET in .env.
Real-money trading is locked: it needs --live AND BOT_ALLOW_LIVE=yes-real-money in the environment, set by the account owner.
"""
