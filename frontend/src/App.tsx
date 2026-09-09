import { useEffect, useMemo, useRef, useState } from "react";
import { api, wsUrl } from "./api";

type Tab = "preview" | "focus" | "autorun" | "video" | "plan" | "album";
type Tool = null | "pa" | "guide" | "solve" | "atlas" | "settings" | "power";

function Hist({ bins }: { bins?: number[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !bins?.length) return;
    const ctx = c.getContext("2d")!;
    const w = (c.width = c.clientWidth * 2);
    const h = (c.height = 108);
    ctx.clearRect(0, 0, w, h);
    const max = Math.max(...bins, 1);
    ctx.fillStyle = "#ff7a18";
    bins.forEach((v, i) => {
      const x = (i / bins.length) * w;
      const bh = (v / max) * (h - 4);
      ctx.fillRect(x, h - bh, w / bins.length, bh);
    });
  }, [bins]);
  return <canvas className="hist" ref={ref} />;
}

function GuideGraph({ samples }: { samples: { ra: number; dec: number }[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const w = (c.width = c.clientWidth * 2);
    const h = (c.height = 240);
    ctx.fillStyle = "#0b0f16";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#222a36";
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();
    const draw = (key: "ra" | "dec", color: string) => {
      ctx.strokeStyle = color;
      ctx.beginPath();
      samples.forEach((s, i) => {
        const x = (i / Math.max(1, samples.length - 1)) * w;
        const y = h / 2 - s[key] * 28;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
    };
    draw("ra", "#6cb6ff");
    draw("dec", "#3ee0a0");
  }, [samples]);
  return <canvas className="guide-graph" ref={ref} />;
}

function SkyMap({ atlas, onGoto }: { atlas: any; onGoto: (id: string) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !atlas) return;
    const ctx = c.getContext("2d")!;
    const w = (c.width = c.clientWidth * 2);
    const h = (c.height = 420);
    ctx.fillStyle = "#05070b";
    ctx.fillRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.46;
    ctx.strokeStyle = "#1c2430";
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
    const project = (alt: number, az: number) => {
      const rad = ((90 - alt) / 90) * r;
      const a = ((az - 180) * Math.PI) / 180;
      return [cx + rad * Math.sin(a), cy - rad * Math.cos(a)];
    };
    for (const s of atlas.stars || []) {
      if (s.alt < 0) continue;
      const [x, y] = project(s.alt, s.az);
      const size = Math.max(1, 4 - s.mag * 0.4);
      ctx.fillStyle = "#dbe7ff";
      ctx.fillRect(x, y, size, size);
    }
    ctx.fillStyle = "#ff7a18";
    for (const o of atlas.dsos || []) {
      if (o.alt < 8) continue;
      const [x, y] = project(o.alt, o.az);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
    if (atlas.mount) {
      const [x, y] = project(atlas.mount.alt, atlas.mount.az);
      ctx.strokeStyle = "#ff7a18";
      ctx.strokeRect(x - 10, y - 8, 20, 16);
    }
  }, [atlas]);
  return (
    <div>
      <canvas className="guide-graph" style={{ height: 210 }} ref={ref} />
      <div className="list" style={{ maxHeight: 180, marginTop: 8 }}>
        {(atlas?.dsos || [])
          .filter((o: any) => o.alt > 25)
          .slice(0, 12)
          .map((o: any) => (
            <button key={o.id} className="item" onClick={() => onGoto(o.id)}>
              <b>{o.name}</b> <span className="muted">{o.id} · 高度 {o.alt.toFixed(0)}°</span>
            </button>
          ))}
      </div>
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<any>(null);
  const [devices, setDevices] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("preview");
  const [tool, setTool] = useState<Tool>(null);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState("");
  const [catalog, setCatalog] = useState<any>(null);
  const [query, setQuery] = useState("");
  const [atlas, setAtlas] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [form, setForm] = useState({
    lat: 31.2304,
    lon: 121.4737,
    focal: 580,
    aperture: 80,
    guide_focal: 240,
    camera: "",
    mount: "",
  });
  const [seq, setSeq] = useState({
    target: "M42",
    exposure: 30,
    count: 10,
    gain: 100,
    filter: "L",
    dither: true,
  });
  const [planTargets, setPlanTargets] = useState<any[]>([]);

  useEffect(() => {
    api.devices().then((d) => {
      setDevices(d);
      setForm((f) => ({ ...f, camera: d.cameras[0], mount: d.mounts[0] }));
    });
    api.status().then(setStatus).catch(() => setStatus(null));
    const ws = new WebSocket(wsUrl());
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "status") setStatus(msg.status);
    };
    return () => ws.close();
  }, []);

  const connected = !!status?.connected;
  const cam = status?.camera;
  const mount = status?.mount;

  const run = async (label: string, fn: () => Promise<any>) => {
    setBusy(label);
    setError("");
    try {
      return await fn();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy("");
    }
  };

  const doPreview = (extra: object = {}) =>
    run("曝光中…", async () => {
      const r = await api.preview(extra);
      setPreview(r);
      return r;
    });

  const doConnect = () =>
    run("连接设备…", async () => {
      const s = await api.connect(form);
      setStatus(s);
    });

  const loadCatalog = async (q = query) => setCatalog(await api.catalog(q));
  const loadAtlas = async () => setAtlas(await api.atlas());
  const loadImages = async () => setImages((await api.images()).images || []);

  useEffect(() => {
    if (tool === "atlas") loadAtlas();
    if (tab === "album") loadImages();
    if (tab === "plan" && !catalog) loadCatalog("");
  }, [tool, tab]);

  const pa = status?.polar?.result;

  const connectScreen = (
    <div className="connect">
      <div className="hero">
        <div className="brand">ALL-SKY · ORGPI</div>
        <h1>橙派天文拍摄系统</h1>
        <p>对标 ASIAIR 的极轴、解析、导星、对焦与计划拍摄工作流</p>
      </div>
      <div className="card">
        <div className="grid2">
          <div>
            <label className="field">主相机</label>
            <select value={form.camera} onChange={(e) => setForm({ ...form, camera: e.target.value })}>
              {(devices?.cameras || []).map((x: string) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="field">赤道仪</label>
            <select value={form.mount} onChange={(e) => setForm({ ...form, mount: e.target.value })}>
              {(devices?.mounts || []).map((x: string) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="field">主镜焦距 (mm)</label>
            <input type="number" value={form.focal} onChange={(e) => setForm({ ...form, focal: +e.target.value })} />
          </div>
          <div>
            <label className="field">口径 (mm)</label>
            <input type="number" value={form.aperture} onChange={(e) => setForm({ ...form, aperture: +e.target.value })} />
          </div>
          <div>
            <label className="field">纬度</label>
            <input type="number" value={form.lat} onChange={(e) => setForm({ ...form, lat: +e.target.value })} />
          </div>
          <div>
            <label className="field">经度</label>
            <input type="number" value={form.lon} onChange={(e) => setForm({ ...form, lon: +e.target.value })} />
          </div>
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button
            className="btn"
            onClick={() =>
              navigator.geolocation.getCurrentPosition((p) =>
                setForm((f) => ({ ...f, lat: p.coords.latitude, lon: p.coords.longitude }))
              )
            }
          >
            使用定位
          </button>
          <button className="btn primary" onClick={doConnect} disabled={!!busy}>
            连接全部设备
          </button>
        </div>
        {error && <p className="err">{error}</p>}
        <p className="muted" style={{ marginTop: 12 }}>
          默认启用模拟器，无需真实相机即可完整体验。Orange Pi 上接入 INDI 后设置 ALLSKY_INDI_HOST 即可控制真实设备。
        </p>
      </div>
    </div>
  );

  const toolPanel = useMemo(() => {
    if (!tool) return null;
    if (tool === "pa") {
      return (
        <div className="panel">
          <h3>极轴校准</h3>
          <p className="muted">全天解析法：拍一张 → 赤道仪转 60° → 再拍一张，得到方位/高度误差。</p>
          <div className="row">
            <button className="btn" onClick={() => run("开始极轴", api.polarStart)}>开始</button>
            <button className="btn primary" onClick={() => run("极轴拍摄", api.polarCapture)}>拍摄并解析</button>
          </div>
          {pa && (
            <>
              <p className={`quality ${pa.quality}`}>总误差 {(Math.abs(pa.total_arcsec) / 60).toFixed(1)}′ · {pa.message}</p>
              <div className="statgrid">
                <div className="stat"><b>方位</b>{(pa.az_arcsec / 60).toFixed(1)}′</div>
                <div className="stat"><b>高度</b>{(pa.alt_arcsec / 60).toFixed(1)}′</div>
              </div>
              <p className="muted">按箭头微调赤道仪极轴（模拟器会立即减小误差）</p>
              <div className="pad">
                <span />
                <button className="pa-arrow" onClick={() => api.polarAdjust(0, 60)}>高度+</button>
                <span />
                <button className="pa-arrow" onClick={() => api.polarAdjust(-60, 0)}>方位-</button>
                <button className="pa-arrow" onClick={() => api.polarAdjust(0, 0)}>OK</button>
                <button className="pa-arrow" onClick={() => api.polarAdjust(60, 0)}>方位+</button>
                <span />
                <button className="pa-arrow" onClick={() => api.polarAdjust(0, -60)}>高度-</button>
              </div>
            </>
          )}
        </div>
      );
    }
    if (tool === "guide") {
      return (
        <div className="panel">
          <h3>导星</h3>
          <div className="row">
            <button className="btn primary" onClick={() => run("导星", api.guideStart)}>开始</button>
            <button className="btn" onClick={() => api.guideStop()}>停止</button>
            <button className="btn" onClick={() => doPreview({ guide: true, exposure: 1 })}>导星预览</button>
          </div>
          <div className="statgrid">
            <div className="stat"><b>RA RMS</b>{status?.guiding?.rms?.ra ?? "–"}″</div>
            <div className="stat"><b>DEC RMS</b>{status?.guiding?.rms?.dec ?? "–"}″</div>
          </div>
          <GuideGraph samples={status?.guiding?.samples || []} />
        </div>
      );
    }
    if (tool === "solve") {
      return (
        <div className="panel">
          <h3>解析 / 居中</h3>
          <div className="row">
            <button className="btn primary" onClick={() => run("解析", () => api.solve(false))}>解析当前图</button>
            <button className="btn" onClick={() => run("同步", () => api.solve(true))}>同步赤道仪</button>
          </div>
          {status?.solve && (
            <div className="kv">
              <b>RA</b><span>{status.solve.ra}</span>
              <b>DEC</b><span>{status.solve.dec}</span>
              <b>视场</b><span>{status.solve.fov_x_deg}° × {status.solve.fov_y_deg}°</span>
              <b>星点</b><span>{status.solve.stars}</span>
            </div>
          )}
        </div>
      );
    }
    if (tool === "atlas") {
      return (
        <div className="panel">
          <h3>星图 / GoTo</h3>
          <div className="row">
            <input placeholder="搜索 M42 / 猎户…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <button className="btn" onClick={() => loadCatalog(query)}>搜索</button>
          </div>
          <div className="list">
            {(catalog?.objects || catalog?.tonight || []).slice(0, 20).map((o: any) => (
              <button key={o.id} className="item" onClick={() => run(`GoTo ${o.id}`, () => api.goto({ id: o.id }))}>
                <b>{o.name_zh || o.name}</b>
                <div className="muted">{o.id} · mag {o.mag} · 高度 {o.alt}°</div>
              </button>
            ))}
          </div>
          <SkyMap atlas={atlas} onGoto={(id) => run("GoTo", () => api.goto({ id }))} />
        </div>
      );
    }
    if (tool === "power") {
      return (
        <div className="panel">
          <h3>电源口</h3>
          {(status?.power?.ports || []).map((p: any) => (
            <div className="row" key={p.id}>
              <span>DC{p.id} {p.name}</span>
              <button className="btn" onClick={() => api.power(p.id, !p.on)}>{p.on ? "关闭" : "打开"}</button>
              <span className="muted">{p.amps}A</span>
            </div>
          ))}
          <p className="muted">输入 {status?.power?.voltage}V · {status?.power?.amps}A</p>
        </div>
      );
    }
    if (tool === "settings") {
      return (
        <div className="panel">
          <h3>设备</h3>
          <div className="kv">
            <b>主相机</b><span>{cam?.name}</span>
            <b>温度</b><span>{cam?.temperature}℃ / {cam?.cooler_power}%</span>
            <b>赤道仪</b><span>{mount?.name} {mount?.ra} {mount?.dec}</span>
            <b>电调焦</b><span>{status?.focuser?.position}</span>
            <b>滤镜</b><span>{status?.wheel?.filter}</span>
          </div>
          <div className="row">
            <button className="btn" onClick={() => api.tracking(!mount?.tracking)}>{mount?.tracking ? "停止跟踪" : "开始跟踪"}</button>
            <button className="btn" onClick={() => api.park()}>回停</button>
            <button className="btn danger" onClick={() => api.disconnect().then(setStatus)}>断开</button>
          </div>
          <div className="log">
            {(status?.logs || []).slice().reverse().map((l: any, i: number) => (
              <div key={i}>{l.t} {l.msg}</div>
            ))}
          </div>
        </div>
      );
    }
    return null;
  }, [tool, status, pa, catalog, atlas, query, cam, mount]);

  if (!connected) return connectScreen;

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">ALL-SKY</div>
        <span className={`chip ${connected ? "on" : ""}`}>{connected ? "已连接" : "未连接"}</span>
        <span className="chip">{mount?.ra} {mount?.dec}</span>
        <span className="chip">HFR {status?.hfr?.toFixed?.(2) ?? preview?.hfr ?? "–"}</span>
        <span className="chip">{cam?.temperature}℃</span>
        <span className="spacer" />
        <span className="chip">{status?.power?.voltage}V</span>
        <span className="chip">{status?.disk_free_gb}GB</span>
      </div>

      <div className="stage">
        <div className="rail">
          {[
            ["pa", "极轴", "PA"],
            ["guide", "导星", "PHD"],
            ["solve", "解析", "Solve"],
            ["atlas", "星图", "GoTo"],
            ["power", "电源", "DC"],
            ["settings", "设备", "EQ"],
          ].map(([id, zh, en]) => (
            <button key={id} className={`tool ${tool === id ? "active" : ""}`} onClick={() => setTool(tool === id ? null : (id as Tool))}>
              <b>{zh}</b><span>{en}</span>
            </button>
          ))}
        </div>

        <div className="sky">
          {preview?.image ? <img src={preview.image} alt="preview" /> : <div className="placeholder">设置曝光后点击拍摄<br />模拟星空将按当前指向生成</div>}
          <div className="crosshair" />
          {busy && <div className="busy">{busy}</div>}
          {error && <div className="busy err">{error}</div>}
        </div>

        {(tool || tab !== "preview") && (
          <div className="side">
            {toolPanel}
            {tab === "focus" && (
              <div className="panel">
                <h3>对焦</h3>
                <p>当前位置 {status?.focuser?.position} · HFR {preview?.hfr ?? status?.hfr}</p>
                <div className="row">
                  <button className="btn" onClick={() => api.focus({ delta: -50 }).then(() => doPreview())}>粗-</button>
                  <button className="btn" onClick={() => api.focus({ delta: -8 }).then(() => doPreview())}>细-</button>
                  <button className="btn" onClick={() => api.focus({ delta: 8 }).then(() => doPreview())}>细+</button>
                  <button className="btn" onClick={() => api.focus({ delta: 50 }).then(() => doPreview())}>粗+</button>
                </div>
                <button className="btn primary" onClick={() => run("自动对焦", api.autofocus)}>自动对焦 (V 曲线)</button>
                <div className="muted">HFR 越小越好。建议 BIN2 / 1–2s 找星。</div>
              </div>
            )}
            {tab === "autorun" && (
              <div className="panel">
                <h3>自动拍摄</h3>
                <label className="field">目标名</label>
                <input value={seq.target} onChange={(e) => setSeq({ ...seq, target: e.target.value })} />
                <div className="grid2">
                  <div><label className="field">曝光秒</label><input type="number" value={seq.exposure} onChange={(e) => setSeq({ ...seq, exposure: +e.target.value })} /></div>
                  <div><label className="field">张数</label><input type="number" value={seq.count} onChange={(e) => setSeq({ ...seq, count: +e.target.value })} /></div>
                </div>
                <div className="row">
                  {(status?.wheel?.filters || []).map((f: string, i: number) => (
                    <button key={f} className={`btn ${seq.filter === f ? "primary" : ""}`} onClick={() => { setSeq({ ...seq, filter: f }); api.filter(i); }}>{f}</button>
                  ))}
                </div>
                <div className="row">
                  <button className="btn primary" onClick={() => run("自动拍摄", () => api.autorunStart({
                    target: seq.target,
                    dither: seq.dither,
                    items: [{ kind: "LIGHT", filter: seq.filter, exposure: seq.exposure, count: seq.count, gain: seq.gain, binning: cam?.binning || 1 }],
                  }))}>开始序列</button>
                  <button className="btn danger" onClick={() => api.autorunStop()}>停止</button>
                </div>
                <p className="muted">进度 {status?.sequencer?.progress?.done || 0}/{status?.sequencer?.progress?.total || 0}</p>
              </div>
            )}
            {tab === "video" && (
              <div className="panel">
                <h3>行星视频</h3>
                <p className="muted">短曝光连续预览，适合木星/土星/月球。</p>
                <button className="btn primary" onClick={() => doPreview({ exposure: 0.05 })}>开始预览</button>
              </div>
            )}
            {tab === "plan" && (
              <div className="panel">
                <h3>今夜计划</h3>
                <p className="muted">选择多个目标，按高度自动排序后依次拍摄。</p>
                <div className="list">
                  {(catalog?.tonight || []).map((o: any) => (
                    <button key={o.id} className="item" onClick={() => setPlanTargets((p) => p.find((x) => x.id === o.id) ? p : [...p, o])}>
                      <b>{o.name_zh}</b> <span className="muted">{o.id} · 高度 {o.alt}°</span>
                    </button>
                  ))}
                </div>
                <h3>队列 {planTargets.length}</h3>
                {planTargets.map((o) => (
                  <div key={o.id} className="item">{o.name_zh}</div>
                ))}
                <button className="btn primary" disabled={!planTargets.length} onClick={() => run("计划拍摄", async () => {
                  for (const t of planTargets) {
                    await api.goto({ id: t.id });
                    await api.autorunStart({
                      target: t.id,
                      ra_hours: t.ra_hours,
                      dec_deg: t.dec_deg,
                      items: [{ kind: "LIGHT", filter: "L", exposure: 8, count: 2, gain: 100, binning: 1 }],
                    });
                  }
                })}>执行多目标计划</button>
              </div>
            )}
            {tab === "album" && (
              <div className="panel">
                <h3>相册</h3>
                <div className="list">
                  {images.map((im) => (
                    <div className="item" key={im.id || im.name}>
                      <b>{im.name}</b>
                      <div className="muted">{im.mtime || im.time} · {im.size_mb ? `${im.size_mb} MB` : ""} {im.hfr ? `HFR ${im.hfr}` : ""}</div>
                    </div>
                  ))}
                  {!images.length && <p className="muted">还没有 FITS。跑一段自动拍摄后会出现在 data/images。</p>}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="dock">
        <div>
          <label className="field">曝光 {cam?.exposure}s · 增益 {cam?.gain} · BIN{cam?.binning}</label>
          <Hist bins={preview?.histogram?.bins} />
        </div>
        <select value={cam?.exposure} onChange={(e) => api.camera({ exposure: +e.target.value })}>
          {[0.05, 0.2, 0.5, 1, 2, 3, 5, 10, 30, 60, 120, 180, 300].map((x) => (
            <option key={x} value={x}>{x}s</option>
          ))}
        </select>
        <select value={cam?.gain} onChange={(e) => api.camera({ gain: +e.target.value })}>
          {[0, 50, 100, 150, 200, 250, 300].map((x) => (
            <option key={x} value={x}>G{x}</option>
          ))}
        </select>
        <select value={cam?.binning || 1} onChange={(e) => api.camera({ binning: +e.target.value })}>
          {[1, 2, 4].map((x) => (
            <option key={x} value={x}>BIN{x}</option>
          ))}
        </select>
        <button className="btn" onClick={() => doPreview({ stack: true })} disabled={!!busy}>叠加</button>
        <button className="btn primary" onClick={() => doPreview()} disabled={!!busy || cam?.exposing}>
          {cam?.exposing ? `剩余 ${cam.remaining}s` : "拍摄"}
        </button>
      </div>
      <div className="tabs">
        {([
          ["preview", "预览"],
          ["focus", "对焦"],
          ["autorun", "自动"],
          ["video", "视频"],
          ["plan", "计划"],
          ["album", "相册"],
        ] as [Tab, string][]).map(([id, label]) => (
          <button key={id} className={`tab ${tab === id ? "active" : ""}`} onClick={() => { setTab(id); if (id !== "preview") setTool(null); }}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
