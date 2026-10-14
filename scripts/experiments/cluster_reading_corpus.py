#!/usr/bin/env python3
"""Offline BERT-CCPoem + K-means exploration of the 3491-work Poeticus reading corpus.

Artifacts stay in poeticus-data, not the tracked Poeticus repository.
Reruns reuse the saved embeddings and projections.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[3] / "poeticus-data"
OUT = ROOT / "reports/recommendations/cluster_full"
CORPUS = ROOT / "reading-corpus/normalized/all_normalized.json"
MODEL = ROOT / "models/BERT_CCPoem_v1"
SEED = 20261014
GROUPS = [8, 16, 24]


def encode_full_poems(poems: list[dict]) -> np.ndarray:
    vectors_file = OUT / "bert_ccpoem_all_3491.npy"
    stamp_file = OUT / "bert_source.sha256"
    current_hash = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    if (
        stamp_file.exists()
        and stamp_file.read_text(encoding="ascii").strip() != current_hash
    ):
        raise ValueError("阅读语料已变化，旧 BERT 缓存不可直接复用；请重新生成实验缓存")
    if not stamp_file.exists():
        previous_metrics = OUT / "cluster_metrics.json"
        if previous_metrics.exists():
            prior_hash = json.loads(previous_metrics.read_text(encoding="utf8"))[
                "corpus_sha256"
            ]
            if prior_hash != current_hash:
                raise ValueError("已有缓存对应的语料版本不同，不能直接复用")
        stamp_file.write_text(current_hash + "\n", encoding="ascii")
    if vectors_file.exists():
        vec = np.load(vectors_file)
        if vec.shape == (len(poems), 512):
            print("复用本地 BERT 向量：", vectors_file, flush=True)
            return vec
        raise ValueError("缓存向量数量与当前语料不一致，请先核对语料版本")
    import sys
    import torch
    from transformers import AutoModel, BertTokenizer

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.corpus.bert_ccpoem_embedding_build import encode_batch

    torch.set_num_threads(4)
    tokenizer = BertTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    lengths = [
        len(tokenizer(p["text"], add_special_tokens=True)["input_ids"]) for p in poems
    ]
    if max(lengths) > 512:
        raise ValueError("有作品超过 BERT 上限，不能无说明地截断")

    shards = []
    model = None
    for start in range(0, len(poems), 240):
        end = min(start + 240, len(poems))
        shard_file = OUT / f"bert_slice_{start:04d}_{end:04d}.npy"
        if shard_file.exists():
            shard = np.load(shard_file)
            if shard.shape != (end - start, 512):
                raise ValueError(f"缓存分片形状不符：{shard_file}")
        else:
            if model is None:
                model = AutoModel.from_pretrained(str(MODEL), local_files_only=True)
                model.eval()
            values = [
                encode_batch(
                    [x["text"] for x in poems[i : min(i + 32, end)]],
                    tokenizer,
                    model,
                    "cpu",
                    torch,
                )
                for i in range(start, end, 32)
            ]
            shard = np.concatenate(values).astype(np.float32)
            np.save(shard_file, shard)
        shards.append(shard)
        print("已编码 / 复用", end, "/", len(poems), flush=True)
    vectors = normalize(np.concatenate(shards)).astype(np.float32)
    assert vectors.shape == (len(poems), 512)
    np.save(vectors_file, vectors)
    print("BERT 向量完成", vectors.shape, flush=True)
    return vectors


def compute(
    poems: list[dict],
    vectors: np.ndarray,
    *,
    model_key: str = "bert",
    embedding_sha256: str | None = None,
) -> tuple[dict, dict]:
    prefix = "qwen_" if model_key == "qwen" else ""
    model_name = "Qwen3-Embedding-0.6B" if model_key == "qwen" else "BERT-CCPoem v1"
    json_file = OUT / f"{prefix}cluster_explorer_data.json"
    metrics_file = OUT / f"{prefix}cluster_metrics.json"
    corpus_sha256 = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    if json_file.exists() and metrics_file.exists():
        d = json.loads(json_file.read_text(encoding="utf-8"))
        previous = json.loads(metrics_file.read_text(encoding="utf-8"))
        if (
            d["n"] == len(poems)
            and previous["corpus_sha256"] == corpus_sha256
            and previous["embedding_model"] == model_name
            and previous.get("vector_dimensions", 512) == vectors.shape[1]
            and previous.get("embedding_file_sha256") == embedding_sha256
        ):
            print("复用已计算的 K-means / PCA / t-SNE", flush=True)
            return d, previous

    t = time.perf_counter()
    decomposer = PCA(n_components=50, svd_solver="randomized", random_state=SEED)
    pcs = decomposer.fit_transform(vectors)
    print("PCA 完成：", round(time.perf_counter() - t, 1), flush=True)
    t = time.perf_counter()
    tsne = TSNE(
        n_components=2,
        perplexity=40,
        max_iter=1000,
        learning_rate="auto",
        init="pca",
        random_state=SEED,
        metric="euclidean",
        method="barnes_hut",
    )
    tsne_xy = tsne.fit_transform(pcs)
    print("t-SNE 完成：", round(time.perf_counter() - t, 1), flush=True)

    labels: dict[str, list[int]] = {}
    cluster_summaries: dict[str, dict] = {}
    metrics: dict[str, object] = {
        "corpus_count": len(poems),
        "corpus_sha256": corpus_sha256,
        "embedding_model": model_name,
        "embedding_file_sha256": embedding_sha256,
        "vector_dimensions": int(vectors.shape[1]),
        "representation": (
            "all original poem text; Qwen SentenceTransformer encode; L2 normalized; 1024d"
            if model_key == "qwen"
            else "all original poem text; full sequence masked mean pooling; L2 normalized; 512d"
        ),
        "projection": "PCA-50; t-SNE-2 on PCA-50",
        "pca_explained_variance_2d": round(
            float(sum(decomposer.explained_variance_ratio_[:2])), 5
        ),
        "silhouette": {},
        "sizes": {},
        "parameters": {
            "random_state": SEED,
            "k": GROUPS,
            "kmeans_n_init": 10,
            "tsne_perplexity": 40,
        },
        "note": "Silhouette is geometry, not poetry category validity; 2D projection may distort neighbors and separations.",
    }
    for k in GROUPS:
        start = time.perf_counter()
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED, max_iter=300)
        yy = km.fit_predict(vectors)
        sil = silhouette_score(
            vectors, yy, metric="cosine", sample_size=900, random_state=SEED
        )
        labels[str(k)] = yy.tolist()
        metrics["silhouette"][str(k)] = round(float(sil), 4)
        groups_by_idx = collections.defaultdict(list)
        for i, label in enumerate(yy):
            groups_by_idx[int(label)].append(i)
        metrics["sizes"][str(k)] = {
            str(group): len(ids) for group, ids in sorted(groups_by_idx.items())
        }
        summary = {}
        for group, ids in groups_by_idx.items():
            authors = collections.Counter(poems[i]["author"] for i in ids)
            centroid = normalize(km.cluster_centers_[group].reshape(1, -1))[0]
            reps = sorted(ids, key=lambda i: -float(vectors[i] @ centroid))[:4]
            summary[str(group)] = {
                "count": len(ids),
                "authors": authors.most_common(3),
                "representatives": reps,
            }
        cluster_summaries[str(k)] = summary
        print(
            "K =",
            k,
            "silhouette =",
            round(float(sil), 4),
            "分群大小 =",
            sorted([len(ii) for ii in groups_by_idx.values()], reverse=True),
            "秒数 =",
            round(time.perf_counter() - start, 1),
            flush=True,
        )

    start = time.perf_counter()
    similarities = vectors @ vectors.T
    top_neighbors = []
    for i, row in enumerate(similarities):
        # Cross-author neighbors, not matched word for word or group membership.
        indices = np.argpartition(-row, 70)[:70]
        ranked = sorted(indices, key=lambda j: -float(row[j]))
        seen = set()
        neighbors = []
        for j in ranked:
            j = int(j)
            if i == j or poems[j]["author"] == poems[i]["author"]:
                continue
            if poems[j]["text"] == poems[i]["text"] or poems[j]["text"] in seen:
                continue
            seen.add(poems[j]["text"])
            neighbors.append([j, round(float(row[j]), 4)])
            if len(neighbors) == 5:
                break
        top_neighbors.append(neighbors)
    del similarities
    print("跨作者近邻完成，秒数：", round(time.perf_counter() - start, 1), flush=True)

    data = {
        "n": len(poems),
        "poems": poems,
        "pca": np.round(pcs[:, :2], 4).tolist(),
        "tsne": np.round(tsne_xy, 4).tolist(),
        "labels": labels,
        "cluster_summaries": cluster_summaries,
        "neighbors": top_neighbors,
        "model": model_name,
    }
    json_file.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    metrics_file.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data, metrics


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>词的星图 · BERT-CCPoem 聚类实验</title>
<style>
:root{color-scheme:light;--ink:#243044;--muted:#64748b;--line:#e2e5e9;--cream:#faf8f4;--accent:#b67d46}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;color:var(--ink);background:#f6f5f1}
header{display:flex;align-items:center;gap:16px;padding:15px 24px;background:#fff;border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{font-family:"Noto Serif CJK SC","Source Han Serif SC","Songti SC",serif;font-weight:750;font-size:24px;letter-spacing:2px}
.sub{font-size:12px;color:var(--muted);margin-top:3px}
.logo{width:12px;height:38px;border-left:3px solid var(--accent);border-right:1px solid #d8b58d}
.controls{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-left:auto}
label.control{font-size:11px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
select,input{border:1px solid #cbd5e1;border-radius:8px;min-height:34px;padding:5px 10px;background:white;color:#293449;font-size:13px}
#search{width:200px}
.shell{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 84px);min-height:550px}
.main{position:relative;overflow:hidden;background:#fff}
#plot{width:100%;height:100%}
.plot-badge{position:absolute;z-index:1;pointer-events:none;top:18px;left:26px;background:#fffffff2;border:1px solid #edf0f2;border-radius:9px;padding:9px 12px;font-size:12px;color:#64748b;max-width:320px;box-shadow:0 2px 8px #24304408}
.plot-badge b{color:#27374a}
.sidebar{overflow-y:auto;border-left:1px solid var(--line);background:var(--cream);padding:20px 20px 35px}
.eyebrow{letter-spacing:2px;font-size:10px;color:var(--accent);font-weight:800;text-transform:uppercase;margin-bottom:9px}
h2{font-size:20px;font-family:"Songti SC","Noto Serif CJK SC",serif;margin:0 0 6px;line-height:1.45}
.section{padding:0 0 18px;margin:0 0 18px;border-bottom:1px solid #e9e1d6}
.muted{color:#798596;font-size:12px;line-height:1.65}
.poem{white-space:pre-wrap;font-family:"Songti SC","STSong","Noto Serif CJK SC",serif;font-size:15px;line-height:2.1;margin:12px 0;color:#3f4550}
.small-head{font-size:12px;font-weight:750;margin:0 0 8px}
.pill{font-size:11px;background:#fff;border:1px solid #dfd9d0;border-radius:18px;padding:3px 8px;display:inline-flex;margin:4px 4px 2px 0}
.linkrow{display:block;width:100%;border:1px solid #e5e0d8;background:#fff;text-align:left;padding:9px 10px;border-radius:8px;margin:7px 0;cursor:pointer;color:#334155}
.linkrow:hover{border-color:#bca07e;background:#fffaf1}
.linkrow .score{float:right;color:#9a784e;font-size:11px}
.cluster{border-radius:8px;border:1px solid #e2ded4;background:#fff;padding:10px;margin:8px 0}
.cluster-head{display:flex;justify-content:space-between;align-items:center;gap:12px}
.cluster-head b{font-size:13px}
.cluster-head span{font-size:12px;color:#768294}
.cluster .muted{margin-top:5px}
button.soft{background:#fff;border:1px solid #dfd8cc;border-radius:7px;color:#65543f;font-size:11px;padding:4px 8px;cursor:pointer}
.stats{font-size:12px;color:#657385;margin-top:6px}
footer{font-size:11px;color:#8692a0;line-height:1.6;padding:12px;border:1px dashed #dadcdd;border-radius:8px;background:#fff}
@media(max-width:980px){.shell{grid-template-columns:1fr;height:auto}.main{height:65vh;min-height:460px}.sidebar{border-left:0;border-top:1px solid var(--line)}}
</style>
</head>
<body>
<header>
<div class="logo"></div>
<div><div class="brand">词的星图</div><div class="sub">BERT-CCPoem · 全量作品聚类 · 离线研究实验</div></div>
<div class="controls">
<label class="control">二维投影
<select id="projection"><option value="tsne">t-SNE · 局部邻近</option><option value="pca">PCA · 整体方向</option></select></label>
<label class="control">颜色含义
<select id="coloring"><option value="8">K-means · 8 类</option><option value="16" selected>K-means · 16 类</option><option value="24">K-means · 24 类</option><option value="author">作者</option></select></label>
<label class="control">搜索作品 / 作者 / 词句<input id="search" placeholder="苏轼、声声慢、春风十里…"></label>
</div>
</header>
<div class="shell">
<main class="main">
<div class="plot-badge"><b id="map-count">3,491 首词</b><br><span id="map-explain">颜色是算法分组，不是文学流派。点击散点查看全文。</span></div>
<div id="plot"></div>
</main>
<aside class="sidebar">
<section class="section">
<div class="eyebrow">SELECTED WORK · 点击散点</div>
<h2 id="work-title">从散点中选择一首词</h2>
<div id="work-meta" class="muted">你可以搜索作品、点击散点，也可以先探索右下方的聚类目录。</div>
<div id="work-body" class="poem"></div>
<div id="work-tags"></div>
</section>
<section class="section">
<div class="eyebrow">VECTOR NEIGHBORS · 向量近邻</div>
<p class="muted">下面的相似度是在原始 512 维空间中计算，并非二维散点距离，也不是文学相似的正确概率。排除同作者。</p>
<div id="neighbors">选择一首词后显示。</div>
</section>
<section class="section">
<div class="eyebrow">CLUSTERS · 浏览分组</div>
<div id="clusters"></div>
</section>
<footer>实验说明：作品正文 → BERT-CCPoem 512 维向量 → K-means 无监督聚类。PCA / t-SNE 只是不同的二维显示方法；二维上的群落可能被拉伸、挤压或人为分开。不要仅凭图形判定文学风格。</footer>
</aside>
</div>
<script>
/* PLOTLY_BUNDLE */
</script>
<script>
const DATA = /* EMBEDDED_DATA */;
const metrics = /* EMBEDDED_METRICS */;
const plot = document.getElementById('plot');
const colorOpt = document.getElementById('coloring');
const projOpt = document.getElementById('projection');
const searchOpt = document.getElementById('search');
const authors = Array.from(new Set(DATA.poems.map(p=>p.author))).sort();
let selectedIndex = -1, focusedCluster = null;
let textQuery = '';
function hue(n,total){return 'hsl(' + Math.round((n*137.508)%360) + ',55%,' + (42+(n%3)*5) + '%)';}
function authorColor(name){return hue(authors.indexOf(name),authors.length);}
function colorOf(i){
  if(colorOpt.value === 'author')return authorColor(DATA.poems[i].author);
  return hue(DATA.labels[colorOpt.value][i],Number(colorOpt.value));
}
function xy(){return DATA[projOpt.value];}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function formatLabel(p){return p.author + ' · ' + p.tune + (p.title?' · '+p.title:'');}
function groupLabel(i){return '第 ' + String(DATA.labels[colorOpt.value][i]+1).padStart(2,'0') + ' 群';}
function matched(i){
  if(textQuery && !(DATA.poems[i].author + DATA.poems[i].tune + (DATA.poems[i].title || '') + DATA.poems[i].text).includes(textQuery))return false;
  if(focusedCluster !== null && colorOpt.value !== 'author' && DATA.labels[colorOpt.value][i] !== focusedCluster)return false;
  return true;
}
function renderedTrace(){
  const coords=xy();
  return {
    type:'scattergl',mode:'markers',
    x:coords.map(p=>p[0]),y:coords.map(p=>p[1]),
    text:DATA.poems.map(p=>esc(formatLabel(p))+'<br>'+esc(p.text.slice(0,63))+'…'),
    hovertemplate:'%{text}<extra></extra>',
    marker:{size:7,color:DATA.poems.map((_,i)=>colorOf(i)),opacity:DATA.poems.map((_,i)=>matched(i)?0.74:0.05)},
  };
}
function refresh(){
  const trace=renderedTrace();
  Plotly.restyle(plot,{'x':[trace.x],'y':[trace.y],'text':[trace.text],'marker.color':[trace.marker.color],'marker.opacity':[trace.marker.opacity]});
  const n=DATA.poems.reduce((count,_,i)=>count+(matched(i)?1:0),0);
  document.getElementById('map-count').textContent=n.toLocaleString('zh-CN')+' / '+DATA.n.toLocaleString('zh-CN')+' 首可见';
  document.getElementById('map-explain').textContent=colorOpt.value==='author'?'颜色区分作者；点击作品查看向量近邻。':'颜色是 K-means 分组；不代表先验文学分类。';
  renderClusters();
  if(selectedIndex>=0)renderWork(selectedIndex);
}
function selectWork(i){
  selectedIndex=i;
  focusedCluster=null;
  textQuery='';
  searchOpt.value='';
  refresh();
  renderWork(i);
  const coords=xy()[i];
  const all=DATA[projOpt.value];
  const minX=Math.min(...all.map(p=>p[0])),maxX=Math.max(...all.map(p=>p[0]));
  const minY=Math.min(...all.map(p=>p[1])),maxY=Math.max(...all.map(p=>p[1]));
  Plotly.relayout(plot,{'xaxis.range':[coords[0]-(maxX-minX)*0.16,coords[0]+(maxX-minX)*0.16],
    'yaxis.range':[coords[1]-(maxY-minY)*0.16,coords[1]+(maxY-minY)*0.16]});
}
function renderWork(i){
  const p=DATA.poems[i];
  document.getElementById('work-title').textContent=p.tune+(p.title?' · '+p.title:'');
  document.getElementById('work-meta').textContent=p.author+' · 源ID '+p.id;
  document.getElementById('work-body').textContent=p.text;
  document.getElementById('work-tags').innerHTML=colorOpt.value==='author'?'<span class="pill">作者着色视图</span>':'<span class="pill">'+esc(groupLabel(i))+'</span>';
  const div=document.getElementById('neighbors');
  div.replaceChildren();
  DATA.neighbors[i].forEach(([j,sim])=>{
    const b=document.createElement('button');b.className='linkrow';
    b.textContent=formatLabel(DATA.poems[j]);
    const score=document.createElement('span');score.className='score';score.textContent=' '+sim.toFixed(3);
    b.appendChild(score);b.addEventListener('click',()=>selectWork(j));div.appendChild(b);
  });
}
function renderClusters(){
 const holder=document.getElementById('clusters');
 holder.replaceChildren();
 if(colorOpt.value==='author'){
   const counts=new Map();
   DATA.poems.forEach(p=>counts.set(p.author,(counts.get(p.author)||0)+1));
   const para=document.createElement('p');para.className='muted';para.textContent='当前按作者上色。选择 K-means 查看算法分组。';
   holder.appendChild(para);
   for(const [name,count] of [...counts].sort((a,b)=>b[1]-a[1]).slice(0,20)){
     const el=document.createElement('span');el.className='pill';el.textContent=name+' '+count;el.style.borderLeft='3px solid '+authorColor(name);holder.appendChild(el);
   }
   return;
 }
 const k=colorOpt.value;
 const clusters=Object.entries(DATA.cluster_summaries[k]).sort((a,b)=>b[1].count-a[1].count);
 const clear=document.createElement('button');clear.className='soft';clear.textContent='显示全部作品';
 clear.addEventListener('click',()=>{focusedCluster=null;refresh();});
 holder.appendChild(clear);
 const metric=document.createElement('div');metric.className='stats';
 metric.textContent='K='+k+' · 原始向量 cosine silhouette ≈ '+metrics.silhouette[k];
 holder.appendChild(metric);
 clusters.forEach(([lab,item])=>{
   const node=document.createElement('div');node.className='cluster';node.style.borderLeft='4px solid '+hue(+lab,+k);
   const head=document.createElement('div');head.className='cluster-head';
   const b=document.createElement('b');b.textContent='第 '+String(+lab+1).padStart(2,'0')+' 群';
   const n=document.createElement('span');n.textContent=item.count+' 首';
   head.appendChild(b);head.appendChild(n);node.appendChild(head);
   const note=document.createElement('div');note.className='muted';
   note.textContent='作者：'+item.authors.map(a=>a[0]+' '+a[1]).join('，');
   node.appendChild(note);
   const rep=document.createElement('div');rep.className='muted';
   rep.textContent='代表：'+item.representatives.slice(0,3).map(i=>DATA.poems[i].author+'《'+DATA.poems[i].tune+'》').join('、');
   node.appendChild(rep);
   const only=document.createElement('button');only.className='soft';only.textContent=focusedCluster===+lab?'取消单独查看':'只看这一群';
   only.addEventListener('click',()=>{focusedCluster=focusedCluster===+lab?null:+lab;refresh();});
   node.appendChild(only);holder.appendChild(node);
 });
}
function resetAxes(){Plotly.relayout(plot,{'xaxis.autorange':true,'yaxis.autorange':true});}
colorOpt.addEventListener('change',()=>{focusedCluster=null;refresh();});
projOpt.addEventListener('change',()=>{refresh();resetAxes();});
searchOpt.addEventListener('input',()=>{textQuery=searchOpt.value.trim();focusedCluster=null;refresh();});
const initialLayout={
 margin:{l:32,r:18,t:16,b:35},paper_bgcolor:'#fff',plot_bgcolor:'#fff',
 xaxis:{showgrid:false,zeroline:false,showticklabels:false,title:{text:''}},
 yaxis:{showgrid:false,zeroline:false,showticklabels:false,title:{text:''}},
 showlegend:false,hovermode:'closest',dragmode:'pan',font:{family:'sans-serif'},
};
Plotly.newPlot(plot,[renderedTrace()],initialLayout,{responsive:true,scrollZoom:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']})
.then(()=>{
 plot.on('plotly_click',event=>{if(event.points&&event.points[0]){selectedIndex=event.points[0].pointNumber;renderWork(selectedIndex);}});
 renderClusters();
});
</script>
</body>
</html>
"""


def render_html(data: dict, metrics: dict, model_key: str = "bert") -> Path:
    from plotly.offline import get_plotlyjs

    bundle = get_plotlyjs()
    html_content = PAGE.replace("BERT-CCPoem", metrics["embedding_model"])
    html_content = html_content.replace(
        "512 维", f"{metrics.get('vector_dimensions', 512)} 维"
    )
    html_content = html_content.replace("/* PLOTLY_BUNDLE */", bundle)
    data_inline = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    metrics_inline = json.dumps(
        metrics, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    html_content = html_content.replace("/* EMBEDDED_DATA */", data_inline)
    html_content = html_content.replace("/* EMBEDDED_METRICS */", metrics_inline)
    output = OUT / (
        "qwen-cluster-explorer.html" if model_key == "qwen" else "cluster-explorer.html"
    )
    output.write_text(html_content, encoding="utf-8")
    print(
        "浏览器可打开：",
        output,
        "大小：",
        round(output.stat().st_size / 1024 / 1024, 2),
        "MB",
        flush=True,
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare BERT and Qwen clustering of 3491 ci poems."
    )
    parser.add_argument("--model", choices=("bert", "qwen"), default="bert")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    poems = []
    for row in raw:
        body = "".join(row["content"]["text"])
        poems.append(
            {
                "id": row["id"],
                "author": row.get("author", ""),
                "tune": row.get("tune", ""),
                "title": row.get("title"),
                "text": body,
            }
        )
    assert len(poems) == 3491
    print("源语料", CORPUS, len(poems), "首", flush=True)
    if args.model == "qwen":
        from verify_qwen_gpu_output import verify_output

        embeddings, embedding_sha256 = verify_output(OUT / "autodl_transfer", CORPUS)
        print("复用已校验的 AutoDL Qwen 向量", embeddings.shape, flush=True)
    else:
        embeddings, embedding_sha256 = encode_full_poems(poems), None
    data, metrics = compute(
        poems, embeddings, model_key=args.model, embedding_sha256=embedding_sha256
    )
    render_html(data, metrics, model_key=args.model)
