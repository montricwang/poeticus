#!/usr/bin/env python3
"""Read-only source and reviewer adjudication; outputs only into a new master directory."""
import collections, hashlib, importlib.util, json, pathlib, re, sys
from zipfile import ZipFile

BASE=pathlib.Path("/home/montric/projects/poeticus-data/critic-methods")
RESULTS=BASE/"results"
REVIEWS=BASE/"reviews_2026-10-22"
INBOX=REVIEWS/"inbox"
OUT=REVIEWS/"master_2026-10-22"
EPUB=BASE/"raw/唐宋词鉴赏辞典.epub"
ORIGINAL=RESULTS/"critic_methods_reviewed_v2_1505.jsonl"
EXPECTED_EPUB="7b3f4efaf574689aba6184cfc1076fb95d9494da96c5fce64a497ed11553d294"
def digest(b): return hashlib.sha256(b).hexdigest()
def read_jsonl(p):
    with p.open(encoding="utf-8") as f:
        for ln in f:
            if ln.strip(): yield json.loads(ln)
def jsonwrite(name, rows):
    path=OUT/name
    with path.open("w",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False)+"\n")
def textwrite(name,content): (OUT/name).write_text(content,encoding="utf-8")
def details(rec):
    no=int(rec.split(":")[0]); idx=int(rec.split(":m")[1])
    essay=essays[no]; return essay,essay["methods"][idx]
def parse_source(essay):
    eid=essay["essay_id"]
    if eid not in paragraphs:
        src=essay["source"]
        q={"EPUB文件":src["epub_file"],"条目锚点":" / ".join(src["entry_anchors"])}
        anchors,ps,sig,readid=parser.parse(q,z,html_cache)
        if readid!=eid or anchors!=src["entry_anchors"]: raise ValueError("essay identity "+eid)
        paragraphs[eid]=ps
    return paragraphs[eid]
def check(essay,e):
    ps=parse_source(essay); p=int(e["paragraph"]); off=int(e["char_start"])
    q=e["quote"]; sha=e["paragraph_sha256"]
    valid=1<=p<=len(ps); txt=ps[p-1] if valid else ""
    flags={"paragraph_exists":valid,"offset_and_exact_quote":valid and txt[off:off+len(q)]==q,
           "paragraph_sha256":valid and digest(txt.encode("utf-8"))==sha}
    return {"paragraph":p,"char_start":off,"quote":q,"expected_sha256":sha,
            "actual_sha256":digest(txt.encode("utf-8")) if valid else None,
            "checks":flags,"verified":all(flags.values())}
if OUT.exists() and any(OUT.iterdir()): raise SystemExit("Refusing to overwrite existing nonempty output: "+str(OUT))
spec=importlib.util.spec_from_file_location("original_critic_runner",RESULTS/"critic_runner.py")
parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
if digest(EPUB.read_bytes())!=EXPECTED_EPUB: raise SystemExit("EPUB SHA256 mismatch")
essays={x["essay_no"]:x for x in read_jsonl(ORIGINAL)}
assert len(essays)==1505
research=[]
for directory in sorted(INBOX.glob("review-*")):
    p=directory/"review.jsonl"
    assert p.is_file()
    research.extend((directory.name,row) for row in read_jsonl(p))
assert len(research)==1858
assert len({(r["category"],r["record_id"]) for _,r in research})==1858
original_count=collections.Counter(r["review_decision"] for _,r in research)
assert original_count=={"accept":769,"revise":945,"reclassify":102,"unresolved":18,"defer":24},original_count
OUT.mkdir(parents=True,exist_ok=True)
paragraphs={};html_cache={};source_checks=[];evidence_by_record={}
with ZipFile(EPUB) as z:
    for group,row in research:
        essay,method=details(row["record_id"])
        assert row["category"]==method["code"],row["record_id"]
        checks=[check(essay,e) for e in method["evidence"]]
        evidence_by_record[row["record_id"]]=checks
        source_checks.append({"record_id":row["record_id"],"category":row["category"],
                              "essay_id":essay["essay_id"],"epub_file":essay["source"]["epub_file"],
                              "entry_anchors":essay["source"]["entry_anchors"],"checks":checks,
                              "all_verified":all(c["verified"] for c in checks)})
    assert sum(len(x["checks"]) for x in source_checks)==5535
    assert all(x["all_verified"] for x in source_checks)
jsonwrite("source-anchor-checks.jsonl",source_checks)

def historical_issues():
    spec=[
      ("TEXT_WORD","text_word_methodology_2026-10-22/citation-audit.json","unresolved_anchors"),
      ("HISTORY","history_methodology_2026-10-22/citation-audit.json","unresolved_anchors"),
      ("PROSODY","prosody_methodology_2026-10-22/citation-audit.json","unresolved_anchors"),
      ("IMAGE","image_methodology_2026-10-22/evidence-verification.json","failures"),
    ]
    for cat,path,key in spec:
        data=json.loads((RESULTS/path).read_text(encoding="utf-8"))
        for item in data[key]: yield cat,path,item
    path="narrative_methodology_2026-10-22/narrative-evidence-audit-exceptions.json"
    for item in json.loads((RESULTS/path).read_text(encoding="utf-8")): yield "NARRATIVE",path,item
    path="structure_methodology_2026-10-22/structure-evidence-audit-exceptions.json"
    for item in json.loads((RESULTS/path).read_text(encoding="utf-8")):
        for check in item["checks"]:
            if not check["strict_verified"]: yield "STRUCTURE",path,{"record_id":item["record_id"],**check}
historical=[]
with ZipFile(EPUB) as z:
    for cat,path,item in historical_issues():
        record_id=item["record_id"]
        essay,method=details(record_id)
        if method["code"]!=cat: raise AssertionError((record_id,cat,method["code"]))
        checked=[check(essay,e) for e in method["evidence"]]
        if not all(c["verified"] for c in checked): raise AssertionError("Historical source mismatch "+record_id)
        q=item.get("quote",item.get("short_quote",""))
        related=[c for c in checked if q in c["quote"] or c["quote"] in q] if q else []
        historical.append({"category":cat,"record_id":record_id,"historical_audit":path,
                           "historical_raised":item,"canonical_evidence":related or checked,
                           "status":"resolved_original_parser",
                           "diagnosis":"旧分类级审计使用不同的 XHTML 段落/文本规范化口径；原始条目解析器完整锚点、引文、偏移与段落哈希匹配"})
assert len(historical)==143,len(historical)
assert collections.Counter(x["category"] for x in historical)=={"TEXT_WORD":41,"HISTORY":29,"PROSODY":8,"IMAGE":10,"NARRATIVE":11,"STRUCTURE":44}
jsonwrite("historical-143.jsonl",historical)
by_record={x["record_id"]:x for x in source_checks}
unresolved=[{"group":g,"record_id":r["record_id"],"category":r["category"],
             "previous_source_review_status":r["source_review_status"],
             "status":"verified_original_parser_not_full_literary_read",
             "evidence":by_record[r["record_id"]]} for g,r in research if r["source_review_status"]=="anchor_unresolved"]
assert len(unresolved)==83,len(unresolved)
jsonwrite("researcher-83.jsonl",unresolved)

def load_map(p):
    return {r["record_id"]:r for r in read_jsonl(p)}
overrides=load_map(REVIEWS/"decision-overrides.jsonl")
prior=load_map(REVIEWS/"adjudicated/decision-adjudication.jsonl")
assert len(overrides)==len(prior)==42 and set(overrides)==set(prior)
ALL_CATS=set(parser.METHODS)
def suggestions(row):
    raw=row.get("cross_category_candidates") or []
    candidates=[]
    for entry in raw:
        head=str(entry).split(":",1)[0].upper().strip()
        if head in ALL_CATS and head not in candidates: candidates.append(head)
    text=row.get("proposed_revision","")
    strong=[]
    for cat in ALL_CATS:
        if re.search(r"(?:归入|改归|主类为|移入|应归于|转入|主分类为)\s*"+cat+r"\b",text,re.I): strong.append(cat)
    external=[x for x in strong if x!=row["category"]]
    if len(external)==1: return external[0],"explicit_revision",candidates
    external=[x for x in candidates if x!=row["category"]]
    if len(external)==1: return external[0],"single_cross_category_candidate",candidates
    return None,"ambiguous_or_submethod_only",candidates
master=[];subsets=collections.defaultdict(list)
for group,row in research:
    rid=row["record_id"];decision=row["review_decision"]
    base={"group":group,"record_id":rid,"category":row["category"],
          "original_reviewer_decision":decision,"source_anchor_status":"verified_original_parser",
          "source_review_status_original":row["source_review_status"],
          "literary_read_depth":"excerpt_only_or_programmatic_full_not_independently_certified",
          "reviewer_evidence_quality":{"extraction_fidelity":row["extraction_fidelity"],
                     "reasoning_quality":row["reasoning_quality"],"category_fit":row["category_fit"]},
          "proposed_revision":row.get("proposed_revision",""),
          "findings":row.get("findings",""),"limitations":row.get("limitations",""),
          "transferable_steps":row.get("transferable_steps",[]),
          "researcher_primary_suggestion":None,"adjudication_basis":"Original reviewer record; controller evidence/status normalization",
          "status":None,"skill_policy":None,"necessary_next_evidence":[]}
    if decision in ("unresolved","defer"):
        a=overrides[rid];b=prior[rid]
        cross=(a["review_decision"]!=b["final_decision"] or
               (a["review_decision"]=="reclassify" and
                b.get("target_category") and a.get("proposed_primary_category")!=b["target_category"]))
        base["adjudication_sources"]={"decision_overrides":a,"prior_adjudicated":b}
        base["researcher_primary_suggestion"]=a.get("proposed_primary_category")
        if cross:
            base.update(status="controller_disagreement_hold",skill_policy="do_not_promote",
                        necessary_next_evidence=["两份主控判定冲突：先确认分析动作的主要对象，再裁定主分类/接受条件"])
            subsets["conflicts"].append(base)
        else:
            base.update(status="bounded_method_adjudicated_not_external_fact_verified",
                        skill_policy="conditional_pilot_only",
                        necessary_next_evidence=["传本、史料、历史音韵或作者意图等外部主张仍待独立核验；不得教作定论"])
            subsets["bounded_method"].append(base)
    elif decision=="accept":
        if row["extraction_fidelity"]!="supported":
            base.update(status="hold_accept_extraction_partial",skill_policy="do_not_promote",
                        necessary_next_evidence=["逐篇核对提炼归纳是否超出原赏析"])
            subsets["high_risk_accept"].append(base)
        elif row["reasoning_quality"]=="supported":
            base.update(status="reviewer_supported_pilot_candidate",skill_policy="limited_ab_pilot",
                        necessary_next_evidence=["尚未完成独立全文文学判断；不得称正式验证"])
            subsets["pilot"].append(base)
        else:
            base.update(status="plausible_interpretation_conditional",skill_policy="conditional_pilot_only",
                        necessary_next_evidence=["说明竞争性读法和原评的推论边界"])
            subsets["conditional"].append(base)
    elif decision=="revise":
        proposal=row.get("proposed_revision","").strip()
        assert proposal
        short=len(proposal)<16
        base.update(status="revision_needs_detail" if short else "revision_candidate_not_applied",
                    skill_policy="do_not_promote_until_edited",
                    necessary_next_evidence=["把建议修订应用到候选方法条目并逐条复核"]+
                      (["当前修改建议过短，需补具体步骤/限制"] if short else []))
        subsets["revisions"].append(base)
    elif decision=="reclassify":
        target,basis,candidates=suggestions(row)
        base.update(status="reclassify_destination_proposed" if target else "reclassify_destination_ambiguous",
                    skill_policy="do_not_promote_until_reclassified",
                    researcher_primary_suggestion=target,
                    category_suggestion_basis=basis,category_candidates=candidates,
                    necessary_next_evidence=["主类改判必须与原方法论证动作逐条核对，兼容跨类次标签"])
        subsets["reclassifications"].append(base)
    else: raise AssertionError(decision)
    master.append(base)
assert len(master)==1858
assert len(subsets["bounded_method"])+len(subsets["conflicts"])==42
assert len(subsets["revisions"])==945
assert len(subsets["reclassifications"])==102
assert len(subsets["pilot"])==254
assert len(subsets["conditional"])+len(subsets["high_risk_accept"])==515
jsonwrite("master-review-1858.jsonl",master)
for name in ["conflicts","bounded_method","pilot","conditional","high_risk_accept","revisions","reclassifications"]:
    jsonwrite(name+".jsonl",subsets[name])

cat_stats={}
pilot_ct=collections.Counter(x["category"] for x in subsets["pilot"])
for cat in parser.METHODS:
    rs=[r for _,r in research if r["category"]==cat]
    if not rs:
        verdict="not_covered_by_six_reviews"
    elif pilot_ct[cat]>=10:
        verdict="small_ab_pilot_from_supported_examples_only"
    elif pilot_ct[cat]>0:
        verdict="exploratory_pilot_tiny_sample_only"
    else:
        verdict="no_supported_accept_basis_for_pilot"
    cat_stats[cat]={"reviewed":len(rs),"pilot_candidates":pilot_ct[cat],
        "original_decisions":dict(collections.Counter(r["review_decision"] for r in rs)),
        "skill_next_step":verdict,"production_ready":False}
by_group={}
for name in sorted(set(g for g,_ in research)):
    rs=[r for g,r in research if g==name]
    by_group[name]={"count":len(rs),"accept":sum(r["review_decision"]=="accept" for r in rs),
      "supported_accept":sum(r["review_decision"]=="accept" and r["reasoning_quality"]=="supported" for r in rs),
      "source_review_status":dict(collections.Counter(r["source_review_status"] for r in rs))}
counts={"input_reviews":1858,"reviewer_decisions":dict(original_count),
        "original_parser_checked_methods":1858,"original_parser_checked_evidence":5611,
        "original_parser_evidence_success":sum(sum(c["verified"] for c in x["checks"]) for x in source_checks),
        "historical_anomalies":143,"historical_resolved_original_parser":len(historical),
        "reviewer_anchor_unresolved":83,"reviewer_anchor_resolved_original_parser":len(unresolved),
        "master_status":dict(collections.Counter(x["status"] for x in master)),
        "cross_decision_conflicts":len(subsets["conflicts"]),
        "reviewer_reading_depth":dict(collections.Counter(r["source_review_status"] for _,r in research)),
        "categories":cat_stats,"groups":by_group,
        "revision_proposal_short_under_16":sum(len(x["proposed_revision"].strip())<16 for x in subsets["revisions"]),
        "reclassifications_with_single_suggested_destination":sum(bool(x.get("researcher_primary_suggestion")) for x in subsets["reclassifications"])}
textwrite("counts.json",json.dumps(counts,ensure_ascii=False,indent=2)+"\n")
lines=["# 主控审查与分歧（2026-10-22）","",
 "本次属于依据六组研究记录、原方法记录及原始 EPUB 的**证据复查与裁定门槛统一**；不宣称独立完成 1,858 篇/条的学术精读。","",
 "## 引文",
 f"- 源记录：{len(source_checks)} 条方法；{counts['original_parser_checked_evidence']} 处证据经原始 parser 严格通过。",
 "- 旧分类审计 143 处与研究员标注的 83 条，分别列出证据；它们是不同口径和集合，不能相加为 226 个独立错误。",
 "- 统一基准：2016 EPUB、原 critic_runner.parse；条目 h3、normaltext/fangsong 段落，1 基段落、0 基 Unicode 字符偏移、UTF-8 字节 SHA256。",
 "- 旧审计差异来源为不同 HTML 段落切分/规范化口径。引文定位通过不等于文学推论、史实或版本学判断通过。","",
 "## 主控门槛",
 f"- 仅研究员支持且提取忠实的有限试用候选：{len(subsets['pilot'])}。",
 f"- 可作假设性解释、必须保留异说：{len(subsets['conditional'])}。",
 f"- 曾建议接受但提取忠实度不足：{len(subsets['high_risk_accept'])}；暂缓。",
 f"- 建议修订但尚未实际改入 Skill：{len(subsets['revisions'])}，其中修改建议过短 {counts['revision_proposal_short_under_16']}。",
 f"- 建议改类但尚未执行：{len(subsets['reclassifications'])}，含单一方向候选 {counts['reclassifications_with_single_suggested_destination']}；其余须人工定主类。",
 f"- 原 42 暂缓/未决中，现有两套裁决意见一致 {len(subsets['bounded_method'])}，互相矛盾 {len(subsets['conflicts'])}；外部事实核验不因方法可教而自动完成。","",
 "## 跨组尺度",
 "- TEXT_WORD：01 组 112/323 accept，02 组 43/323；TIME_SPACE：05 组 80/201，06 组 154/200。",
 "- 这不是相同标准下随机抽样的可比质量率。跨组 accepted/core 的含义需限定到受证据支撑的具体方法动作，不把多数票当学术验收。","",
 "## 十四类 Skill 可试用性","",
 "| 分类 | 本轮记录 | 严格受支持的小试候选 | 下一步 |","|---|---:|---:|---|"]
for cat,c in cat_stats.items():
    lines.append(f"| {cat} | {c['reviewed']} | {c['pilot_candidates']} | {c['skill_next_step']} |")
lines+=["","全部处于**候选 Skill 的小规模 AB 试用**门槛，均未成为生产 Agent 已验证 Skill。",
 "## 七处两套裁定冲突",""]
for item in subsets["conflicts"]:
    a=item["adjudication_sources"]["decision_overrides"];b=item["adjudication_sources"]["prior_adjudicated"]
    lines.append(f"- {item['record_id']} {item['category']}：override={a['review_decision']} → {a.get('proposed_primary_category')}；adjudicated={b['final_decision']} → {b.get('target_category')}。需复核主分析动作，暂不移入正式 Skill。")
lines+=["","## 共享方法与边界",
 "- TEXT_WORD × COUNTERFACTUAL：字词微观差异可做替换实验，但比较对象须同语法/语境。",
 "- NARRATIVE × TIME_SPACE × STRUCTURE：人称、时序、场景转折可协作，但不可混同叙述次序与史实时序。",
 "- IMAGE × ALLEGORY × AESTHETICS：意象出现是文本证据；象征寄托和审美效果是可争议解释。",
 "- ALLUSION × HISTORY × CONTEXT × INTERTEXT：识典与文本对读可共享检索证据，但典源、历史事件、作者生平分别确证。",
 "- DEBATE × PROSODY × TEXT_WORD：争鸣、词律判别与异文校勘可交叉，音韵、版本归属不能凭赏析片语断定。",
 "## 待完成（数量准确）","",
 f"- 学术精读与独立事实核验：本轮没有把 {len(master)} 条逐条升级为独立深度验证。",
 f"- 原 revise 945 条：修订建议已保留，但对正式 Skill 的实际改写为 0；短建议 {counts['revision_proposal_short_under_16']} 条。",
 f"- 原 reclassify 102 条：方向已归档，实际方法库改类 0；另有原 unresolved/defer 中 {len(subsets['conflicts'])} 条主控冲突。",
 "- 7 条冲突与外部版本/历史音韵等未取证主张继续以明确缺口状态保存；并非引用锚点仍坏。",
 "- 不进行生产集成。下一阶段以已受支持实例试验方法组织、组合加载和工具选择。"]
textwrite("quality-report.md","\n".join(lines)+"\n")
textwrite("cross-category.md","\n".join(lines[lines.index("## 共享方法与边界"):])+"\n")
readme="""# Poeticus 文学方法主控审查：独立产物

- 源材料未修改：results 下原始 source/coding、原始六组 inbox JSONL、历史 Skill 候选。
- source-anchor-checks.jsonl：1,858 条的全部 5,535 处原始方法证据定位。
- historical-143.jsonl：历史分类级异常逐项重算，保留当时错误报告与当前原 parser 证据。
- researcher-83.jsonl：研究员标为 anchor_unresolved 的逐条证据。
- master-review-1858.jsonl：全部研究员意见与主控门槛；不能据此宣称文学独立精读。
- conflicts.jsonl：7 条现存主控意见冲突，不能无痕覆盖。
- bounded_method.jsonl：原未决/暂缓、方法有条件裁决一致的 35 条；不代表外部史实确证。
- pilot.jsonl、conditional.jsonl、high_risk_accept.jsonl、revisions.jsonl、reclassifications.jsonl：互斥审查清单。
- counts.json、quality-report.md、cross-category.md：汇总与交叉类边界。
- validation.json：文件 SHA-256 与断言结果。

本目录只由 audit_master.py 在原始 WSL 数据集上运行生成。
"""
textwrite("README.md",readme)
files=sorted(p for p in OUT.iterdir() if p.is_file())
validation={"source_epub_sha256":EXPECTED_EPUB,"all_evidence_verified":True,
 "input_six_groups":len(by_group),"review_count":len(master),"historic_resolved":143,"reviewer_unresolved_anchor_resolved":83,
 "sha256":{p.name:digest(p.read_bytes()) for p in files}}
textwrite("validation.json",json.dumps(validation,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:counts[k] for k in ("input_reviews","original_parser_checked_evidence","historical_resolved_original_parser","reviewer_anchor_resolved_original_parser","master_status","cross_decision_conflicts","revision_proposal_short_under_16","reclassifications_with_single_suggested_destination")},ensure_ascii=False))
