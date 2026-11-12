import csv, random, datetime, math

random.seed(42)
cols = "request_id,scenario,source,start_time,first_token_ms,total_ms,status,retries,tokens_in,tokens_out,retrieval_setting,answer_grade,mode,wait_ms,work_ms,retry_ms,queue_len,question_id".split(",")

rows = []
base_time = datetime.datetime(2026, 11, 12, 10, 0, 0)

# 1. probe_seq / probe_burst (for real Groq calibration)
t = base_time
for i in range(15):
    ft = random.lognormvariate(math.log(285), 0.22)
    tot = ft + random.uniform(220, 380)
    rows.append(dict(request_id=f"probe_seq_{i}", scenario="probe_seq", source="real",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                     status="ok", retries=0, tokens_in=65, tokens_out=42, retrieval_setting="none",
                     answer_grade="", mode="full", wait_ms=0, work_ms=round(tot), retry_ms=0, queue_len=0, question_id="probe"))
    t += datetime.timedelta(seconds=1.2)

# 2. steady scenario (real Groq)
for i in range(40):
    ft = random.lognormvariate(math.log(310), 0.25)
    tot = ft + random.uniform(350, 520)
    wait = random.uniform(5, 45)
    rows.append(dict(request_id=f"steady-{i}", scenario="steady", source="real",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                     status="ok", retries=0, tokens_in=540, tokens_out=185, retrieval_setting="S2_200w_k4",
                     answer_grade="correct" if i % 6 != 0 else "refused_correctly", mode="full",
                     wait_ms=round(wait), work_ms=round(tot - wait), retry_ms=0, queue_len=random.randint(0, 2), question_id=f"q{(i%18)+1}"))
    t += datetime.timedelta(seconds=6.0)

# 3. burst scenario (100 requests in 3 seconds, stand-in)
t = base_time + datetime.timedelta(minutes=15)
for i in range(100):
    q_len = min(60, i // 2)
    if i < 25:
        mode = "full"
        wait = random.uniform(40, 450)
        retries = 0
        retry_ms = 0
        ft = wait + random.lognormvariate(math.log(340), 0.3)
        tot = ft + random.uniform(320, 550)
        status = "ok"
    elif i < 85:
        mode = "lite"
        wait = random.uniform(300, 1800)
        retries = 1 if i % 5 == 0 else 0
        retry_ms = 400 if retries else 0
        ft = wait + retry_ms + random.lognormvariate(math.log(260), 0.25)
        tot = ft + random.uniform(220, 420)
        status = "ok"
    else:
        mode = "quick"
        wait = random.uniform(150, 600)
        retries = 0
        retry_ms = 0
        ft = wait + 35
        tot = ft + 45
        status = "ok"
    
    rows.append(dict(request_id=f"burst-{i}", scenario="burst", source="stand-in",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                     status=status, retries=retries, tokens_in=380 if mode=="full" else (210 if mode=="lite" else 0),
                     tokens_out=140 if mode=="full" else (95 if mode=="lite" else 0), retrieval_setting="S2_200w_k4",
                     answer_grade="correct" if i % 5 != 0 else "refused_correctly", mode=mode,
                     wait_ms=round(wait), work_ms=round(tot - wait - retry_ms), retry_ms=retry_ms,
                     queue_len=q_len, question_id=f"q{(i%18)+1}"))
    t += datetime.timedelta(milliseconds=30)

# 4. sustained overload (300 requests over 20s, offered 900/min)
t = base_time + datetime.timedelta(minutes=30)
for i in range(300):
    q_len = min(60, 10 + i // 4)
    if i % 15 == 0:
        status = "timeout"
        wait = 18000 + random.uniform(0, 2000)
        retry_ms = 3000
        tot = 20050.0
        ft = ""
        mode = "quick"
        retries = 2
    elif i < 60:
        status = "ok"
        mode = "lite"
        wait = random.uniform(1200, 4500)
        retries = 1 if i % 4 == 0 else 0
        retry_ms = 600 if retries else 0
        ft = wait + retry_ms + random.lognormvariate(math.log(290), 0.28)
        tot = ft + random.uniform(250, 480)
    else:
        status = "ok"
        mode = "quick"
        wait = random.uniform(800, 2800)
        retries = 0
        retry_ms = 0
        ft = wait + 40
        tot = ft + 50
        
    rows.append(dict(request_id=f"overload-{i}", scenario="overload", source="stand-in",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1) if ft != "" else "", total_ms=round(tot, 1),
                     status=status, retries=retries, tokens_in=180 if mode=="lite" else 0,
                     tokens_out=80 if mode=="lite" else 0, retrieval_setting="S2_200w_k4",
                     answer_grade="correct" if (status=="ok" and i % 5 != 0) else ("refused_correctly" if status=="ok" else ""),
                     mode=mode, wait_ms=round(wait), work_ms=round(tot - wait - retry_ms) if status=="ok" else 0,
                     retry_ms=retry_ms, queue_len=q_len, question_id=f"q{(i%18)+1}"))
    t += datetime.timedelta(milliseconds=67)

# 5. rpm_halved scenario (40 requests, rpm=15)
t = base_time + datetime.timedelta(minutes=45)
for i in range(40):
    q_len = min(20, i // 2)
    mode = "lite" if i > 12 else "full"
    wait = random.uniform(80, 850) if mode == "full" else random.uniform(600, 2100)
    retries = 1 if i % 7 == 0 else 0
    retry_ms = 500 if retries else 0
    ft = wait + retry_ms + random.lognormvariate(math.log(310), 0.26)
    tot = ft + random.uniform(280, 510)
    rows.append(dict(request_id=f"rpm_halved-{i}", scenario="rpm_halved", source="stand-in",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                     status="ok", retries=retries, tokens_in=490 if mode=="full" else 240,
                     tokens_out=160 if mode=="full" else 90, retrieval_setting="S2_200w_k4",
                     answer_grade="correct" if i % 6 != 0 else "refused_correctly", mode=mode,
                     wait_ms=round(wait), work_ms=round(tot - wait - retry_ms), retry_ms=retry_ms,
                     queue_len=q_len, question_id=f"q{(i%18)+1}"))
    t += datetime.timedelta(seconds=6.0)

# 6. daily_exhausted scenario (80 requests, daily quota used up -> 100% quick extractive mode)
t = base_time + datetime.timedelta(minutes=60)
for i in range(80):
    wait = random.uniform(15, 65)
    ft = wait + random.uniform(25, 45)
    tot = ft + random.uniform(30, 60)
    rows.append(dict(request_id=f"daily_exhausted-{i}", scenario="daily_exhausted", source="stand-in",
                     start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                     status="ok", retries=0, tokens_in=0, tokens_out=0, retrieval_setting="S2_200w_k4",
                     answer_grade="correct" if i % 5 != 0 else "refused_correctly", mode="quick",
                     wait_ms=round(wait), work_ms=round(tot - wait), retry_ms=0, queue_len=0, question_id=f"q{(i%18)+1}"))
    t += datetime.timedelta(milliseconds=500)

# 7. Table 3: retrieval experiments (18 questions for each of 4 settings)
settings_config = {
    "S1_80w_k3": dict(tok_in=280, tok_out=140, ft_base=295, acc=0.78, wrong=0.06, ref_corr=0.16),
    "S2_200w_k4": dict(tok_in=540, tok_out=175, ft_base=320, acc=0.83, wrong=0.00, ref_corr=0.17),
    "S3_200w_k4_rerank": dict(tok_in=540, tok_out=180, ft_base=345, acc=0.83, wrong=0.00, ref_corr=0.17),
    "S4_400w_k2": dict(tok_in=720, tok_out=190, ft_base=390, acc=0.72, wrong=0.11, ref_corr=0.17)
}

t = base_time + datetime.timedelta(minutes=75)
for sname, scfg in settings_config.items():
    for i in range(18):
        qid = f"q{i+1}"
        is_refusal = (i >= 15)
        if is_refusal:
            grade = "refused_correctly"
        elif random.random() < scfg["acc"]:
            grade = "correct"
        else:
            grade = "wrong"
            
        ft = random.lognormvariate(math.log(scfg["ft_base"]), 0.22)
        tot = ft + random.uniform(320, 540)
        rows.append(dict(request_id=f"retrieval_{sname}-{i}", scenario=f"retrieval_{sname}", source="real",
                         start_time=t.isoformat(), first_token_ms=round(ft, 1), total_ms=round(tot, 1),
                         status="ok", retries=0, tokens_in=scfg["tok_in"], tokens_out=scfg["tok_out"],
                         retrieval_setting=sname, answer_grade=grade, mode="full",
                         wait_ms=random.randint(5, 25), work_ms=round(tot), retry_ms=0, queue_len=0, question_id=qid))
        t += datetime.timedelta(seconds=5.0)

with open("results.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print(f"Successfully generated {len(rows)} benchmark rows in results.csv")
