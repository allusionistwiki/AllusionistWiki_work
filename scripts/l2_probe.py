import json, sys, time
sys.path.insert(0, "C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/scripts")
from adjudicate_l2 import INSTR, compact_member, parse_json_lenient
from openai import OpenAI

RUN = "20261024T1608_fc8d"
q = [json.loads(l) for l in open(
    "C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/allusionist_v2/L2/runs/%s/adjudication-queue.jsonl" % RUN,
    encoding="utf-8")][:2]
batch = [{"id": g["id"], "edge_types": g["edge_types"],
          "members": [compact_member(m) for m in g["members"][:10]]} for g in q]
prompt = INSTR + json.dumps(batch, ensure_ascii=False)
print("prompt_chars=", len(prompt))
c = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="sk-l2", timeout=600, max_retries=0)
t0 = time.time()
r = c.chat.completions.create(model="swift-1.5-iq3_xxs", temperature=1.0, max_tokens=1500,
                             messages=[{"role": "user", "content": prompt}])
el = time.time() - t0
txt = r.choices[0].message.content or ""
print("elapsed=%.1f completion_tokens=%s finish=%s" % (
    el, r.usage.completion_tokens if r.usage else "?", r.choices[0].finish_reason))
print("RAW_HEAD:", txt[:400].replace("\n", " | ")[:400])
parsed = parse_json_lenient(txt)
print("PARSED_OK:", bool(parsed and parsed.get("results")))
