kis-account prints JSON with mode, masked account, currency KRW and domestic_summary.
Whitelist dnca_tot_amt, tot_evlu_amt, scts_evlu_amt as original decimal strings. Accept one summary object or a one-element list; require all three numeric fields.
Errors are generic English messages, never raw exception/vendor text. Reuse KisClient via a thin public balance method; select TR ID from config.mode.
Use credential-derived token directory under KIS_TOKEN_DIR, without changing other commands. No new dependency or schema.
