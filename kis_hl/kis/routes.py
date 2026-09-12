"""Exact KIS account query routes from the official generated samples."""

from datetime import datetime


def account_route(
    kind, *, exchange, symbol, date_from, date_to, price, paper, older_history
):
    domestic = "/uapi/domestic-stock/v1/trading/"
    overseas = "/uapi/overseas-stock/v1/trading/"
    q = {}
    width = 0
    if kind == "domestic_balance":
        path, live, sim, width = (
            domestic + "inquire-balance",
            "TTTC8434R",
            "VTTC8434R",
            100,
        )
        q = dict(
            AFHR_FLPR_YN="N",
            OFL_YN="",
            INQR_DVSN="02",
            UNPR_DVSN="01",
            FUND_STTL_ICLD_YN="N",
            FNCG_AMT_AUTO_RDPT_YN="N",
            PRCS_DVSN="00",
        )
    elif kind == "overseas_balance":
        path, live, sim, width = (
            overseas + "inquire-balance",
            "TTTS3012R",
            "VTTS3012R",
            200,
        )
        q = dict(OVRS_EXCG_CD=exchange, TR_CRCY_CD="USD")
    elif kind in {"domestic_history", "overseas_history"}:
        for value in (date_from, date_to):
            if len(value) != 8:
                raise ValueError("History dates must be YYYYMMDD")
            datetime.strptime(value, "%Y%m%d")
        if date_from > date_to:
            raise ValueError("Reversed history dates")
        if kind == "domestic_history":
            path = domestic + "inquire-daily-ccld"
            width = 100
            live, sim = (
                ("CTSC9215R", "VTSC9215R")
                if older_history
                else ("TTTC0081R", "VTTC0081R")
            )
            q = dict(
                INQR_STRT_DT=date_from,
                INQR_END_DT=date_to,
                SLL_BUY_DVSN_CD="00",
                PDNO=symbol,
                CCLD_DVSN="00",
                INQR_DVSN="01",
                INQR_DVSN_3="00",
                ORD_GNO_BRNO="",
                ODNO="",
                INQR_DVSN_1="",
            )
        else:
            path, live, sim, width = (
                overseas + "inquire-ccnl",
                "TTTS3035R",
                "VTTS3035R",
                200,
            )
            q = dict(
                PDNO="" if paper else (symbol or "%"),
                ORD_STRT_DT=date_from,
                ORD_END_DT=date_to,
                SLL_BUY_DVSN="00",
                CCLD_NCCS_DVSN="00",
                OVRS_EXCG_CD="" if paper else exchange,
                SORT_SQN="DS",
                ORD_DT="",
                ORD_GNO_BRNO="",
                ODNO="",
            )
    elif kind == "domestic_orders":
        path, live, sim, width = (
            domestic + "inquire-psbl-rvsecncl",
            "TTTC0084R",
            None,
            100,
        )
        q = dict(INQR_DVSN_1="0", INQR_DVSN_2="0")
    elif kind == "overseas_orders":
        path, live, sim, width = overseas + "inquire-nccs", "TTTS3018R", None, 200
        q = dict(OVRS_EXCG_CD=exchange, SORT_SQN="DS")
    elif kind == "domestic_buying_power":
        path, live, sim = domestic + "inquire-psbl-order", "TTTC8908R", "VTTC8908R"
        q = dict(
            PDNO=symbol,
            ORD_UNPR=price,
            ORD_DVSN="00",
            CMA_EVLU_AMT_ICLD_YN="N",
            OVRS_ICLD_YN="N",
        )
    elif kind == "domestic_sellable":
        path, live, sim = domestic + "inquire-psbl-sell", "TTTC8408R", None
        q = dict(PDNO=symbol)
    elif kind == "overseas_buying_power":
        path, live, sim = overseas + "inquire-psamount", "TTTS3007R", "VTTS3007R"
        q = dict(OVRS_EXCG_CD=exchange, OVRS_ORD_UNPR=price, ITEM_CD=symbol)
    else:
        raise ValueError("Unsupported KIS account inquiry")
    if width:
        q.update({f"CTX_AREA_FK{width}": "", f"CTX_AREA_NK{width}": ""})
    return path, live, sim, q, width
