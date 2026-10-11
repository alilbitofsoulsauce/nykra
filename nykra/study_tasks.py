"""Distinct algorithmic coding challenges for model-in-the-loop evaluation.

The agent receives descriptions and training examples, not reference functions.
Held-out inputs use a different deterministic seed; no task source is persisted
in Nykra SQLite. This is a small local benchmark, not SWE-bench or blind data.
"""
from __future__ import annotations

import json
import random

TASKS = {
    "unique-window": "Write solve(text) returning the length of the longest contiguous substring containing no repeated characters. Empty text returns 0.",
    "maximum-subarray": "Write solve(values) returning the greatest sum of a nonempty contiguous subsequence. Return 0 for an empty list. Lists can contain all negative integers.",
    "min-cover-window": "Write solve(text, required) returning the shortest contiguous substring of text that contains every character of required with its multiplicity. If ties, choose earliest. Return '' if impossible or required is empty.",
    "nonoverlap-intervals": "Write solve(intervals) returning the maximum number of mutually nonoverlapping half-open intervals [start,end] with start < end. End equal to next start is allowed.",
    "trapped-water": "Write solve(heights) returning the total water trapped between bars of nonnegative integer heights; heights may be empty.",
    "next-greater": "Write solve(values) returning a list where each element is the first strictly greater value to its right; use -1 if none. Values may be negative.",
    "common-prefix": "Write solve(words) returning the longest common prefix of all strings. Return '' for an empty list. Repetition and empty strings are possible.",
    "subsequence-count": "Write solve(text, pattern) returning the number of distinct index subsequences of text that equal pattern. The empty pattern has exactly one match; an impossible pattern has zero.",
}


def oracle(name: str, *args):
    if name == "unique-window":
        s, = args
        best=0
        for i in range(len(s)):
            seen=set()
            for j in range(i,len(s)):
                if s[j] in seen:break
                seen.add(s[j])
                best=max(best,j-i+1)
        return best
    if name == "maximum-subarray":
        values, = args
        if not values:return 0
        return max(sum(values[i:j]) for i in range(len(values))
                   for j in range(i+1,len(values)+1))
    if name == "min-cover-window":
        s, required=args
        if not required:return ""
        target={v:required.count(v) for v in required}
        best=None
        for i in range(len(s)):
            counts={}
            for j in range(i,len(s)):
                ch=s[j]
                counts[ch]=counts.get(ch,0)+1
                if all(counts.get(c,0)>=n for c,n in target.items()):
                    candidate=s[i:j+1]
                    if best is None or len(candidate)<len(best):best=candidate
                    break
        return best or ""
    if name == "nonoverlap-intervals":
        intervals, = args
        selected=[]
        for a,b in sorted(intervals,key=lambda x:(x[1],x[0])):
            if not selected or a>=selected[-1][1]:selected.append((a,b))
        return len(selected)
    if name == "trapped-water":
        heights, = args
        volume=0
        for i in range(1,len(heights)-1):
            volume+=max(0,min(max(heights[:i+1]),max(heights[i:]))-heights[i])
        return volume
    if name == "next-greater":
        values, = args
        out=[]
        for i,v in enumerate(values):
            out.append(next((k for k in values[i+1:] if k>v),-1))
        return out
    if name == "common-prefix":
        words, = args
        if not words:return ""
        common=""
        for i,ch in enumerate(words[0]):
            if all(len(word)>i and word[i]==ch for word in words):
                common+=ch
            else:break
        return common
    if name == "subsequence-count":
        text, pattern=args
        memo=[0]*(len(pattern)+1)
        memo[0]=1
        for ch in text:
            for j in range(len(pattern)-1,-1,-1):
                if ch==pattern[j]:memo[j+1]+=memo[j]
        return memo[-1]
    raise KeyError(name)


def cases(task_id: str, *, heldout: bool):
    if task_id not in TASKS:raise KeyError(task_id)
    rng=random.Random(("nykra-blind-b-" if heldout else "nykra-train-a-")+task_id)
    n=40 if heldout else 18
    cases=[]
    # Every held-out input is disjoint from the training set, including
    # fixed edge cases and accidental duplicates from the RNG.
    training_keys=({json.dumps(arguments,sort_keys=True) for arguments,_ in cases_for_training(task_id)}
                   if heldout else set())
    heldout_seen=set()
    i=0
    retries=0
    while i<n:
        if task_id=="unique-window":
            s="".join(rng.choices("aabcdeefg",k=rng.randrange(0,20)))
            if not heldout and i==0:s=""
            if not heldout and i==1:s="abba"
            arguments=[s]
        elif task_id=="maximum-subarray":
            values=[rng.randrange(-11,12) for _ in range(rng.randrange(0,15))]
            if not heldout and i==0:values=[]
            if not heldout and i==1:values=[-9,-2,-7]
            arguments=[values]
        elif task_id=="min-cover-window":
            s="".join(rng.choices("aabbccdef",k=rng.randrange(0,16)))
            need="".join(rng.choices("aabbcdex",k=rng.randrange(0,6)))
            if not heldout and i==0:s,need="ADOBECODEBANC","ABC"
            if not heldout and i==1:s,need="aab","aa"
            if not heldout and i==2:s,need="abcdef",""
            if heldout and i==0:s,need="CABXABBC","ABC"
            if heldout and i==1:s,need="bbaaac","aaab"
            if heldout and i==2:s,need="abcdef","zz"
            arguments=[s,need]
        elif task_id=="nonoverlap-intervals":
            intervals=[]
            for _ in range(rng.randrange(0,13)):
                a=rng.randrange(-12,13)
                intervals.append([a,a+rng.randrange(1,7)])
            if not heldout and i==0:intervals=[]
            if not heldout and i==1:intervals=[[0,2],[2,4],[1,3]]
            arguments=[intervals]
        elif task_id=="trapped-water":
            heights=[rng.randrange(0,10) for _ in range(rng.randrange(0,18))]
            if not heldout and i==0:heights=[]
            if not heldout and i==1:heights=[0,1,0,2,1,0,1,3,2,1,2,1]
            arguments=[heights]
        elif task_id=="next-greater":
            values=[rng.randrange(-6,9) for _ in range(rng.randrange(0,16))]
            if not heldout and i==0:values=[]
            if not heldout and i==1:values=[2,1,2,4,3]
            arguments=[values]
        elif task_id=="common-prefix":
            base="".join(rng.choices("abcdef",k=rng.randrange(0,6)))
            words=[base+"".join(rng.choices("xyzabcd",k=rng.randrange(0,9)))
                   for _ in range(rng.randrange(0,8))]
            if not heldout and i==0:words=[]
            if not heldout and i==1:words=["flower","flow","flight"]
            arguments=[words]
        else:
            s="".join(rng.choices("abca",k=rng.randrange(0,13)))
            pattern="".join(rng.choices("abc",k=rng.randrange(0,7)))
            if not heldout and i==0:s,pattern="rabbbit","rabbit"
            if not heldout and i==1:s,pattern="aaaa","aa"
            if not heldout and i==2:s,pattern="xyz",""
            if heldout and i==0:s,pattern="babgbag","bag"
            if heldout and i==1:s,pattern="mississippi","issi"
            if heldout and i==2:s,pattern="aaaa",""
            arguments=[s,pattern]
        if heldout:
            signature=json.dumps(arguments,sort_keys=True)
            if signature in training_keys or signature in heldout_seen:
                retries+=1
                if retries>20000:
                    raise RuntimeError("could not build disjoint held-out dataset")
                continue
            heldout_seen.add(signature)
        cases.append((arguments,oracle(task_id,*arguments)))
        i+=1
    return cases


def cases_for_training(task_id: str):
    return cases(task_id,heldout=False)
