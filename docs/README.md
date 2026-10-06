# Chi muc docs — doc gi truoc
> Toan bo so duoi la walk-forward 5 nam, chi phi gate Bybit; paper moi la kiem sach.
## 1. Chu tai khoan doc theo thu tu nay
1. OWNER_SUMMARY_VI (2026-10-06) 2. QUICKSTART_VI (2026-10-06) 3. GLOSSARY_VI (2026-10-06) 4. BOT_RUNBOOK_VI (2026-10-06) 5. TESTNET_PLAN_VI (2026-10-06) 6. DEPLOYMENT_PLAN_VI (2026-10-06) 7. FINAL_REPORT_VI (2026-10-06)
## 2. Ky su / agent doc them
EXECUTIVE_SUMMARY_EN (2026-10-06); CLOSED_DIRECTIONS (2026-10-06); RESEARCH_INDEX (2026-10-06); BOT_EXECUTION (2026-10-06); docs/opencode/OPENCODE_VF_COMMON (luat worker vf).
## 3. Moi file tra loi gi (ngay = git log -1 %cs)
- OWNER_SUMMARY_VI (2026-10-06): chay gi (BOT G2 + carry f=0.25), ky vong 4-6%/thang, 4 dieu kien go-live.
- QUICKSTART_VI (2026-10-06): 10 buoc paper -> testnet -> live trong 1 trang.
- GLOSSARY_VI (2026-10-06): tu dien BOT/book/dip/carry/basis/sigma/4 clocks.
- BOT_RUNBOOK_VI (2026-10-06): lenh dong bang, cai dat Bybit UTA 5x, van hanh hang ngay.
- TESTNET_PLAN_VI (2026-10-06): ke hoach testnet 7 ngay, chi kiem mechanics.
- DEPLOYMENT_PLAN_VI (2026-10-06): ky vong dang ky truoc + 4 cua go-live/14-56 ngay/dung.
- FINAL_REPORT_VI (2026-10-06): bao cao hop nhat, dinh nghia R/W/DD, so G2/MANUAL.
- EXECUTIVE_SUMMARY_EN (2026-10-06): ban EN gop so G2/carry/venue/clock cho ky su.
- CLOSED_DIRECTIONS (2026-10-06): huong nao da dong, huong nao con mo, khong lam lai.
- RESEARCH_INDEX (2026-10-06): muc luc 326 bao cao research/diag/tournament.
- BOT_EXECUTION (2026-10-06): mirror paper/testnet/live, PostOnly/SL-TP/risk guard.
- DATA_CATALOG (2026-09-30): cu/tham khao — cac store du lieu local con giu.
- WEB_DEPLOY (2026-10-02): cu/tham khao — FE Vercel + BE 8724 qua Cloudflare tunnel.
- WEB_SECURITY_REVIEW_20261002 (2026-10-02): cu/tham khao — review phan quyen web.
## 4. 5 script quan trong + lenh OOS hang tuan
- scripts/daily_status.py: trang thai 1 trang hang ngay (backend/plan/bot/carry/edge).
- scripts/weekly_report.py: bao cao tuan theo runner (return/DD/win/divergence).
- scripts/alert_watch.py: canh bao CRITICAL + toast Windows + alerts.log.
- scripts/restart_all.sh: khoi phuc sau reboot (backend -> 6 bot paper -> carry).
- scripts/bot_preflight.py: check chi-doc truoc testnet/live (key/Hedge/Cross/5x/von).
- OOS hang tuan: `.venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py --fetch --run`
