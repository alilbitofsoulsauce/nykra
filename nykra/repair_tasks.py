"""Fixed micro-repository repair tasks with independent local regression oracles.

Public cases and hidden cases are disjoint by serialized input. Source and
oracles are local fixtures; this is NOT a third-party blind SWE-bench study.
"""
from __future__ import annotations

import csv
import io
import json
import random

TASKS = {
    "reservation-gaps": {
        "description": (
            "Implement solve(start, end, bookings). Return sorted half-open free "
            "intervals [a,b] within [start,end]. Bookings are [a,b] and can overlap, "
            "be unsorted, fall outside the window, or be empty/invalid (a>=b, ignore). "
            "Merge overlapping/touching occupied intervals; never return zero-length gaps."
        ),
        "buggy_source": (
            "def solve(start, end, bookings):\n"
            "    free = []\n"
            "    cursor = start\n"
            "    for a,b in bookings:\n"
            "        if a > cursor:\n"
            "            free = free + [[cursor,a]]\n"
            "        cursor = b\n"
            "    if cursor < end:\n"
            "        free = free + [[cursor,end]]\n"
            "    return free\n"
        ),
    },
    "ledger-undo": {
        "description": (
            "Implement solve(events) returning account balances as a lexicographically "
            "sorted list [[account,balance],...]. Events are dictionaries. deposit/withdraw "
            "have id, account, amount (positive integer), type. Duplicate id: ignore "
            "subsequent occurrences. Withdrawals exceeding current account balance "
            "are ignored but still consume their id. A cancel event has id, target "
            "and reverses the first previously applied deposit or withdrawal with "
            "that id, at most once; invalid or already cancelled target is ignored. "
            "Cancellation may make a balance negative. Account is created as soon "
            "as a deposit/withdraw is first seen, including rejected withdrawals. "
            "Process in event order."
        ),
        "buggy_source": (
            "def solve(events):\n"
            "    accounts = {}\n"
            "    for e in events:\n"
            "        if e['type'] == 'deposit':\n"
            "            k = e['account']\n"
            "            accounts[k] = accounts.get(k,0) + e['amount']\n"
            "        elif e['type'] == 'withdraw':\n"
            "            k = e['account']\n"
            "            accounts[k] = accounts.get(k,0) - e['amount']\n"
            "    return [[k,accounts[k]] for k in sorted(accounts)]\n"
        ),
    },
    "csv-records": {
        "description": (
            "Implement solve(text) parsing valid comma-delimited CSV into a list "
            "of rows (lists of strings). Quoted fields may contain commas, CRLF "
            "line breaks and doubled double-quote escapes. CRLF or LF separate "
            "unquoted records. Preserve empty fields; an empty input is [], "
            "and a final record separator does not create an extra empty row. "
            "Inputs are valid CSV; do not import libraries or call object methods."
        ),
        "buggy_source": (
            "def solve(text):\n"
            "    if not text: return []\n"
            "    return [line.split(',') for line in text.split('\\n')]\n"
        ),
    },
    "normalized-path": {
        "description": (
            "Implement solve(base, relative). base is a canonical absolute POSIX "
            "path with no trailing slash (except '/'). relative must not begin "
            "with '/' and must not contain a backslash; return None otherwise. "
            "Normalize repeated '/', '.' and '..' components of relative. "
            "A '..' that would escape above base must return None. "
            "Return the resulting absolute path with no trailing slash, preserving "
            "case and ordinary filename characters."
        ),
        "buggy_source": (
            "def solve(base, relative):\n"
            "    if relative.startswith('/'): return None\n"
            "    return base + '/' + relative\n"
        ),
    },
}


def oracle(task: str, arguments: list):
    if task=="reservation-gaps":
        start,end,bookings=arguments
        if end<=start:return []
        occupied=sorted((max(start,a),min(end,b)) for a,b in bookings
                        if b>a and b>start and a<end)
        result=[];cursor=start
        for a,b in occupied:
            if a>cursor:result.append([cursor,a])
            cursor=max(cursor,b)
        if cursor<end:result.append([cursor,end])
        return result
    if task=="ledger-undo":
        events,=arguments
        balances={};seen=set();applied={};cancelled=set()
        for event in events:
            key=event["id"]
            if key in seen:continue
            seen.add(key)
            kind=event["type"]
            if kind=="cancel":
                ref=event["target"]
                if ref in applied and ref not in cancelled:
                    acc,delta=applied[ref]
                    balances[acc]-=delta
                    cancelled.add(ref)
            else:
                account=event["account"];amount=event["amount"]
                if account not in balances:balances[account]=0
                delta=amount if kind=="deposit" else -amount
                if kind=="deposit" or balances[account]>=amount:
                    balances[account]+=delta
                    applied[key]=(account,delta)
        return [[k,balances[k]] for k in sorted(balances)]
    if task=="csv-records":
        text,=arguments
        if text=="":return []
        return list(csv.reader(io.StringIO(text,newline="")))
    if task=="normalized-path":
        base,relative=arguments
        if relative.startswith("/") or "\\" in relative:return None
        components=[]
        for part in relative.split("/"):
            if part in ("","."):continue
            if part=="..":
                if not components:return None
                components.pop()
            else:components.append(part)
        prefix="" if base=="/" else base
        return (prefix+"/"+"/".join(components)).rstrip("/") or "/"
    raise KeyError(task)


def cases(task:str,*,heldout:bool)->list[tuple[list,object]]:
    if task not in TASKS:raise KeyError(task)
    rng=random.Random(("nykra-native-hidden-v1:" if heldout else "nykra-native-train-v1:")+task)
    n=32 if heldout else 14
    entries=[];seen=set()
    def add(args):
        key=json.dumps(args,ensure_ascii=False,sort_keys=True)
        if key not in seen:
            seen.add(key)
            entries.append((args,oracle(task,args)))
    if not heldout:
        base={
            "reservation-gaps":[[0,20,[[6,9],[2,4]]],[2,12,[[0,6],[6,10]]],[1,8,[]]],
            "ledger-undo":[[[{"id":"a","type":"deposit","account":"X","amount":5},{"id":"a","type":"deposit","account":"X","amount":5}]],
                            [[{"id":"a","type":"deposit","account":"X","amount":8},{"id":"b","type":"cancel","target":"a"}]]],
            "csv-records":[['a,b\r\nc,d\r\n'], ['"a,b",z'], ['"a""b",c'], ['']],
            "normalized-path":[["/srv/data","a/../b"],["/srv","../etc"],["/","x/./y"],["/srv","/etc"]],
        }
        for a in base[task]:add(a)
    else:
        # Disjoint special cases not revealed in model training feedback.
        hold={
            "reservation-gaps":[[-10,5,[[0,3],[-7,-4]]]],
            "ledger-undo":[[[{"id":"a","type":"withdraw","account":"X","amount":8},{"id":"b","type":"cancel","target":"a"}]]],
            "csv-records":[['"a\r\nb",z\r\nq,r'], ['"a,b","c""d"']],
            "normalized-path":[["/data","a/../../escape"],["/a","x\\\\y"]],
        }
        for a in hold[task]:add(a)
    attempts=0
    while len(entries)<n:
        attempts+=1
        if attempts>10000:raise RuntimeError("cannot generate distinct test inputs")
        if task=="reservation-gaps":
            start=rng.randint(-15,15);end=start+rng.randint(1,28)
            bookings=[]
            for _ in range(rng.randint(0,9)):
                a=rng.randint(start-20,end+20)
                b=a+rng.randint(-3,13)
                bookings.append([a,b])
            args=[start,end,bookings]
        elif task=="ledger-undo":
            events=[];used=[]
            for i in range(rng.randint(2,14)):
                typ=rng.choice(["deposit","withdraw","withdraw","cancel"])
                eid=("e"+str(i)) if rng.random()>.17 or not used else rng.choice(used)
                if eid not in used:used.append(eid)
                if typ=="cancel":events.append({"id":eid,"type":"cancel","target":rng.choice(used) if used else "missing"})
                else:events.append({"id":eid,"type":typ,"account":rng.choice(["A","B","C"]),"amount":rng.randint(1,15)})
            args=[events]
        elif task=="csv-records":
            buf=io.StringIO(newline="")
            writer=csv.writer(buf,lineterminator=rng.choice(["\r\n","\n"]))
            for _ in range(rng.randint(1,6)):
                row=[]
                for j in range(rng.randint(1,5)):
                    value="".join(rng.choice(["a","b","z",",",'"',"\n","\r\n",""]) for _ in range(rng.randint(0,6)))
                    row.append(value)
                writer.writerow(row)
            raw=buf.getvalue()
            if rng.random()<.25 and raw.endswith("\r\n"):raw=raw[:-2]
            if rng.random()<.25 and raw.endswith("\n"):raw=raw[:-1]
            args=[raw]
        else:
            base=rng.choice(["/","/tmp","/srv/data","/a/b"])
            segs=[rng.choice(["a","b","..",".","","file.txt","résumé","x y"]) for _ in range(rng.randint(0,10))]
            rel="/".join(segs)
            if rng.random()<.07:rel="/"+rel
            if rng.random()<.07:rel=rel+"\\x"
            args=[base,rel]
        add(args)
    return entries
