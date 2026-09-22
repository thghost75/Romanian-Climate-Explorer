import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDownToLine, Check, ChevronRight, CloudRain, Grid2X2, MapPin, Search, Thermometer, TrendingUp, X, CalendarDays, Trophy, History, Zap, Sun, Moon } from 'lucide-react';
import snapshot from './data.json';
import boundary from './romania.json';
import { ArchivePane } from './ArchivePane';
import { inlineSVGTheme } from './svg-theme.js';
import type { ArchiveTab, ArchiveChange } from './archive-engine.js';

type Annual = { year:number; temp:number|null; tempAnomaly:number|null; rain:number|null; rainAnomaly:number|null };
type Station = { id:string; name:string; lat:number; lon:number; first:string; last:string; coverage:number|null; history:Annual[] };
type Metric = 'temp'|'rain';
type View = 'dashboard'|'heatmap'|'compare';
const stations=snapshot.stations as Station[];
const LAST_YEAR=snapshot.lastYear;
const FIRST_YEAR=snapshot.firstYear;
const years=Array.from({length:LAST_YEAR-FIRST_YEAR+1},(_,i)=>FIRST_YEAR+i);
const tidy=(s:string)=>s.toLocaleLowerCase().replace(/(^|[ -])\p{L}/gu,x=>x.toLocaleUpperCase());
const normalize=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const unit=(m:Metric)=>m==='temp'?'°C':'mm';
const fmt=(x:number|null|undefined,n=1)=>x==null?'—':x.toLocaleString('en-GB',{maximumFractionDigits:n,minimumFractionDigits:n});
const signed=(x:number|null|undefined)=>x==null?'—':`${x>0?'+':''}${fmt(x)}`;
const annual=(s:Station,y:number)=>s.history.find(r=>r.year===y);
const anomaly=(r:Annual|undefined,m:Metric)=>r?.[m==='temp'?'tempAnomaly':'rainAnomaly']??null;
const colors=['#5ddbc8','#ffa765','#aab5ff'];
const anomalyColor=(v:number|null,m:Metric)=>v===null?'#354658':v<-(m==='temp'?1:150)?'#529be6':v<0?'#80cce0':v<(m==='temp'?1:150)?'#e6c99d':'#f39169';
const projection=(lon:number,lat:number)=>[30+(lon-20.1)*62,440-(lat-43.4)*62/Math.cos(46*Math.PI/180)];
function geometryPaths(g:any):string[]{
  if(g.type==='FeatureCollection')return g.features.flatMap(geometryPaths);
  if(g.type==='Feature')return geometryPaths(g.geometry);
  if(g.type==='GeometryCollection')return g.geometries.flatMap(geometryPaths);
  const polys=g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];
  return polys.map((poly:number[][][])=>poly.map(ring=>ring.map((c,i)=>(i?'L':'M')+projection(c[0],c[1]).join(',')).join('')+'Z').join(''));
}
const countryPaths=geometryPaths(boundary);
function download(blob:Blob,name:string){const href=URL.createObjectURL(blob);const a=document.createElement('a');a.href=href;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);}

function App(){
  const [theme,setTheme]=useState<'light'|'dark'>(()=>document.documentElement.dataset.theme==='light'?'light':'dark');
  useEffect(()=>{document.documentElement.dataset.theme=theme;try{localStorage.setItem('wxprobs-theme',theme);}catch{/* Private or file-based browsers may disable storage. */}},[theme]);
  const [selected,setSelected]=useState('0-20000-0-15420');
  const [metric,setMetric]=useState<Metric>('temp');
  const [view,setView]=useState<View>('dashboard');
  const [section,setSection]=useState<ArchiveTab>('overview');
  const [month,setMonth]=useState(new Date().getMonth()+1);
  const [day,setDay]=useState(new Date().getDate());
  const [normal,setNormal]=useState('1991-2020');
  const [archiveYear,setArchiveYear]=useState(LAST_YEAR);
  const [query,setQuery]=useState('');
  const [year,setYear]=useState(LAST_YEAR);
  const [start,setStart]=useState(1961);
  const [compare,setCompare]=useState([stations.find(s=>s.name.includes('CLUJ'))!.id,stations.find(s=>s.name==='CONSTANTA')!.id]);
  const [notice,setNotice]=useState('');
  const station=stations.find(s=>s.id===selected)!;
  const current=annual(station,year);
  const filtered=stations.filter(s=>normalize(s.name+' '+s.id).includes(normalize(query)));
  const compared=[station,...compare.filter(id=>id!==selected).map(id=>stations.find(s=>s.id===id)!)];
  const selectStation=(id:string)=>{setCompare(ids=>ids.map(value=>value===id?selected:value));setSelected(id);setNotice('');};
  const archiveChange=(change:ArchiveChange)=>{if(change.station)selectStation(change.station);if(change.tab)setSection(change.tab);if(change.year!==undefined)setArchiveYear(change.year);};
  const calendarControls=<div className="archive-controls"><div className="calendar-label"><CalendarDays size={18}/><span>Calendar day</span></div><label>Month<select aria-label="Calendar month" value={month} onChange={e=>{const value=Number(e.target.value);setMonth(value);setDay(d=>Math.min(d,new Date(2000,value,0).getDate()));}}>{Array.from({length:12},(_,i)=><option key={i} value={i+1}>{new Date(2000,i,1).toLocaleString('en-GB',{month:'long'})}</option>)}</select></label><label>Day<select aria-label="Calendar day" value={day} onChange={e=>setDay(Number(e.target.value))}>{Array.from({length:new Date(2000,month,0).getDate()},(_,i)=><option key={i} value={i+1}>{i+1}</option>)}</select></label><button className="text-button" onClick={()=>{const today=new Date();setMonth(today.getMonth()+1);setDay(today.getDate());}}>Today</button>{section!=='on-day'&&<label className="normal-control">Climate normal<select aria-label="Climate normal" value={normal} onChange={e=>setNormal(e.target.value)}>{['1961-1990','1971-2000','1981-2010','1991-2020'].map(n=><option key={n}>{n}</option>)}</select></label>}</div>;
  const changeStart=(value:number)=>{setStart(value);setYear(y=>Math.max(y,value));};
  function exportCSV(){
    const chosen=view==='compare'?compared:[station];
    const rows=[['Station','WIGOS ID','Year','Mean temperature (C)','Temperature anomaly (C; 1991-2020)','Precipitation (mm)','Precipitation anomaly (mm; 1991-2020)'],
      ...chosen.flatMap(s=>s.history.filter(r=>r.year>=start).map(r=>[s.name,s.id,r.year,r.temp??'',r.tempAnomaly??'',r.rain??'',r.rainAnomaly??'']))];
    const csv=rows.map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');
    download(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}),`WxProbs-${view==='compare'?'comparison':station.id}-${start}-${LAST_YEAR}.csv`);
    setNotice('CSV saved with the displayed annual records.');
  }
  return <div className="app">
    <header className="topbar"><div className="brand"><img className="brand-logo" src="/rce-logo.png?v=a70634ef7831" alt="Romanian Climate Explorer by WxProbs" width="2172" height="724" /></div><div className="top-actions"><button className="theme-toggle" type="button" aria-label={`Switch to ${theme==='dark'?'light':'dark'} mode`} title={`Switch to ${theme==='dark'?'light':'dark'} mode`} onClick={()=>setTheme(value=>value==='dark'?'light':'dark')}>{theme==='dark'?<Sun size={18}/>:<Moon size={18}/>}<span>{theme==='dark'?'Light mode':'Dark mode'}</span></button>{section==='overview'&&<button className="export-button" aria-label="Export annual CSV" onClick={exportCSV}><ArrowDownToLine size={16}/><span>Export annual CSV</span></button>}</div></header>
    <div className="workspace">
      <aside className="sidebar"><div className="sidebar-heading"><span className="eyebrow">Station network</span><span className="count">160</span></div><label className="search"><Search size={17}/><input aria-label="Find a station" placeholder="Find a station…" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button aria-label="Clear search" onClick={()=>setQuery('')}><X size={14}/></button>}</label><div className="list-caption">{filtered.length} stations · ANM + WMO</div><div className="station-list">{filtered.map(s=><button key={s.id} onClick={()=>selectStation(s.id)} className={'station-button '+(s.id===selected?'selected':'')} aria-pressed={s.id===selected}><MapPin size={15}/><span><strong>{tidy(s.name)}</strong><small>{s.id}</small></span>{s.id===selected&&<ChevronRight size={15}/>}</button>)}{!filtered.length&&<p className="empty-list">No matching stations. Try a name or WIGOS identifier.</p>}</div><div className="sidebar-footer"><p><strong>Archive updated</strong><span>Through {snapshot.snapshotDate}<br/>Daily data checks</span></p></div></aside>
      <main>
        <div className="workspace-heading"><div><span className="eyebrow">Explore the archive</span><h1>{section==='on-day'?'On this day in Romania':tidy(station.name)}</h1><p>{section==='on-day'?'Historical records across all 160 stations':<>{station.lat.toFixed(3)}°N · {station.lon.toFixed(3)}°E <span className="divider">/</span> {station.id}</>}</p></div>{section==='overview'&&<div className="metric-switch" aria-label="Climate variable"><button aria-pressed={metric==='temp'} className={metric==='temp'?'active':''} onClick={()=>setMetric('temp')}><Thermometer size={16}/>Temperature</button><button aria-pressed={metric==='rain'} className={metric==='rain'?'active':''} onClick={()=>setMetric('rain')}><CloudRain size={16}/>Precipitation</button></div>}</div>
        <nav className="primary-tabs" aria-label="Explorer sections">{([{id:'overview',label:'Overview',icon:Grid2X2},{id:'on-day',label:'On this day',icon:CalendarDays},{id:'records',label:'Records',icon:Trophy},{id:'temperature',label:'Temperature',icon:Thermometer},{id:'rainfall',label:'Rainfall',icon:CloudRain},{id:'extremes',label:'Extremes',icon:Zap},{id:'history',label:'History',icon:History}] as const).map(tab=><button key={tab.id} aria-current={section===tab.id?'page':undefined} className={section===tab.id?'active':''} onClick={()=>setSection(tab.id)}><tab.icon size={17}/>{tab.label}</button>)}</nav>
        {section==='overview'&&<><div className="archive-shortcuts"><button onClick={()=>setSection('on-day')}><CalendarDays size={21}/><span><strong>On this day</strong><small>Records across Romania · {new Date(2000,month-1,day).toLocaleDateString('en-GB',{day:'numeric',month:'long'})}</small></span><ChevronRight size={18}/></button><button onClick={()=>setSection('extremes')}><Zap size={21}/><span><strong>Historic events</strong><small>Heatwaves, cold spells and extreme rainfall</small></span><ChevronRight size={18}/></button><button onClick={()=>setSection('history')}><History size={21}/><span><strong>Explore a year</strong><small>Daily weather, monthly comparisons and indices</small></span><ChevronRight size={18}/></button></div>
        <div className="toolbar"><nav aria-label="Workspace views">{([{id:'dashboard',label:'Annual overview',icon:Grid2X2},{id:'heatmap',label:'Anomaly heatmap',icon:Activity},{id:'compare',label:'Compare stations',icon:TrendingUp}] as const).map(v=><button key={v.id} aria-pressed={view===v.id} className={view===v.id?'active':''} onClick={()=>setView(v.id)}><v.icon size={16}/>{v.label}</button>)}</nav><label className="period">Period<select aria-label="Chart period" value={start} onChange={e=>changeStart(Number(e.target.value))}><option value={1961}>1961–{LAST_YEAR}</option><option value={1991}>1991–{LAST_YEAR}</option><option value={2011}>2011–{LAST_YEAR}</option></select></label></div>
        <div className="year-control"><label htmlFor="year">Explore year <strong>{year}</strong></label><input id="year" aria-label="Explore year" type="range" min={start} max={LAST_YEAR} value={year} onChange={e=>setYear(Number(e.target.value))}/><span>{LAST_YEAR}</span><button onClick={()=>setYear(LAST_YEAR)} disabled={year===LAST_YEAR}>Latest full year</button></div>
        <div className="metrics"><MetricCard label={`Mean temperature · ${year}`} value={fmt(current?.temp)} units="°C" icon={<Thermometer size={18}/>} tone="warm"/><MetricCard label={`Temperature anomaly · ${year}`} value={signed(current?.tempAnomaly)} units="°C" note="relative to 1991–2020" tone={(current?.tempAnomaly??0)>=0?'warm':'cool'}/><MetricCard label={`Precipitation total · ${year}`} value={fmt(current?.rain,0)} units="mm" icon={<CloudRain size={18}/>} tone="cool"/></div>
        {view==='dashboard'&&<div className="dashboard-grid"><section className="panel map-panel"><PanelTitle eyebrow="01 / Station network" title="A view across Romania" aside={<span className="subtle-tag">160 locations</span>}/><RomaniaMap station={station} onSelect={selectStation} metric={metric} year={year}/><div className="map-legend"><span>{metric==='temp'?'Cooler':'Drier'}</span><i/><span>{metric==='temp'?'Warmer':'Wetter'}</span><span className="missing-key">Grey: no eligible anomaly</span></div><p className="caption">Station anomalies in {year} · baseline 1991–2020</p></section><section className="panel trend-panel"><PanelTitle eyebrow="02 / Through the years" title={metric==='temp'?'Annual temperature':'Annual precipitation'} aside={<ChartSave target="main-chart" title={`${station.name} · Annual ${metric==='temp'?'temperature':'precipitation'} · ${start}–${LAST_YEAR}`} setNotice={setNotice}/>}/><div className="chart-readout"><strong>{fmt(current?.[metric],metric==='temp'?1:0)}<small> {unit(metric)}</small></strong><span>{year} · {current?.[metric]==null?'No eligible annual value':'ANM annual summary'}</span></div><TimeChart id="main-chart" stationList={[station]} metric={metric} year={year} setYear={setYear} start={start}/><p className="caption">Point to a year to explore · missing observations remain gaps</p></section><section className="panel anomaly-panel"><PanelTitle eyebrow="03 / Against the normal" title={metric==='temp'?'Warmer and cooler years':'Wetter and drier years'} aside={<span className="subtle-tag">1991–2020 baseline</span>}/><TimeChart id="anomaly-chart" stationList={[station]} metric={metric} year={year} setYear={setYear} start={start} anomalies/><p className="caption">{metric==='temp'?'Temperature departure in °C':'Precipitation departure in mm'} · each bar is one year</p></section><section className="panel heat-panel"><PanelTitle eyebrow="04 / At a glance" title="The pattern by decade" aside={<button className="text-button" onClick={()=>setView('heatmap')}>Explore <ChevronRight size={14}/></button>}/><Heatmap station={station} metric={metric} year={year} start={start} setYear={setYear} compact/></section></div>}
        {view==='heatmap'&&<section className="panel full-panel"><PanelTitle eyebrow="Annual departures / 1991–2020 baseline" title={`${tidy(station.name)} · anomaly heatmap`} aside={<span className="subtle-tag">{unit(metric)}</span>}/><p className="section-description">Choose a year to inspect its annual {metric==='temp'?'temperature':'precipitation'} and departure from the normal.</p><Heatmap station={station} metric={metric} year={year} start={start} setYear={setYear}/><p className="caption">Grey tiles have no eligible value or baseline. Colours describe station observations, not regional estimates.</p></section>}
        {view==='compare'&&<section className="panel full-panel"><PanelTitle eyebrow="Station analytics / shared annual scale" title="Different places. The same years." aside={<ChartSave target="comparison-chart" title={`Station comparison · ${metric==='temp'?'temperature °C':'precipitation mm'} · ${start}–${LAST_YEAR}`} setNotice={setNotice}/>}/><div className="comparison-pickers"><div><span className="legend-dot" style={{background:colors[0]}}/><span>{tidy(station.name)}<small>Selected station</small></span></div>{compare.map((id,i)=><label key={i}><span className="legend-dot" style={{background:colors[i+1]}}/><select aria-label={`Comparison station ${i+1}`} value={id} onChange={e=>setCompare(ids=>ids.map((v,n)=>n===i?e.target.value:v))}>{stations.filter(s=>s.id!==selected&&s.id!==compare[1-i]).map(s=><option value={s.id} key={s.id}>{tidy(s.name)}</option>)}</select></label>)}</div><TimeChart id="comparison-chart" stationList={compared} metric={metric} year={year} setYear={setYear} start={start}/><div className="comparison-values">{compared.map((s,i)=><div key={s.id}><span className="legend-dot" style={{background:colors[i]}}/><span>{tidy(s.name)}</span><strong>{fmt(annual(s,year)?.[metric])} {unit(metric)}</strong><small>{year}</small></div>)}</div><p className="caption">Annual station summaries. Site altitude and exposure differ; these lines are not a national trend estimate.</p></section>}
        </>}
        {section==='overview'&&<div className="archive-section-heading"><span className="eyebrow">Calendar-day climatology</span><h2>What is usual on this date?</h2></div>}
        {section==='extremes'&&<div className="archive-section-heading"><span className="eyebrow">Historic events</span><h2>Heat, cold, rain and dry spells</h2></div>}
        {calendarControls}
        <ArchivePane state={{station:selected,tab:section,year:archiveYear,month,day,normal}} onChange={archiveChange}/>
        <footer><span>© WxProbs <b>·</b> Observations: ANM <b>·</b> Locations: ANM / WMO OSCAR</span><span>Observations through {snapshot.snapshotDate}</span></footer>
        <div className="notice" role="status">{notice&&<><Check size={15}/>{notice}<button onClick={()=>setNotice('')} aria-label="Dismiss message"><X size={14}/></button></>}</div>
      </main>
    </div>
  </div>;
}
function PanelTitle({eyebrow,title,aside}:{eyebrow:string;title:string;aside?:React.ReactNode}){return <div className="panel-title"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{aside}</div>;}
function MetricCard({label,value,units,note,icon,tone}:{label:string;value:string;units:string;note?:string;icon?:React.ReactNode;tone:string}){return <section className={'metric-card '+tone}><div><span>{label}</span>{icon}</div><strong>{value}<small>{units}</small></strong><p>{note||'Quality-checked annual observations'}</p></section>;}

function RomaniaMap({station,onSelect,metric,year}:{station:Station;onSelect:(id:string)=>void;metric:Metric;year:number}){
  const [x,y]=projection(station.lon,station.lat);
  return <svg className="romania-map" viewBox="0 0 650 470" role="group" aria-label="Interactive map of 160 Romanian weather stations"><defs><radialGradient id="mapGlow"><stop stopColor="#123f4b"/><stop offset="1" stopColor="#102330"/></radialGradient></defs><rect width="650" height="470" fill="#101f2b" rx="8"/>{[22,24,26,28].map(l=><g key={l}><path d={`M${projection(l,49)[0]},15 V450`} stroke="#20313d" strokeDasharray="3 6"/><text x={projection(l,44)[0]} y="455" fill="#728c9e" fontSize="12" textAnchor="middle">{l}°E</text></g>)}{[44,46,48].map(l=><g key={l}><path d={`M15,${projection(20,l)[1]} H635`} stroke="#20313d" strokeDasharray="3 6"/><text x="8" y={projection(20,l)[1]-6} fill="#728c9e" fontSize="12">{l}°N</text></g>)}{countryPaths.map((d,i)=><path key={i} d={d} fill="url(#mapGlow)" stroke="#497082" strokeWidth="1.2" fillRule="evenodd"/>)}{stations.map(s=>{const [cx,cy]=projection(s.lon,s.lat);const a=anomaly(annual(s,year),metric);return <circle key={s.id} role="button" aria-label={`${tidy(s.name)}: ${a==null?'no eligible anomaly':signed(a)+' '+unit(metric)}`} tabIndex={0} cx={cx} cy={cy} r={s.id===station.id?6:3.5} fill={anomalyColor(a,metric)} stroke={s.id===station.id?'#fff':'#0c1c28'} strokeWidth={s.id===station.id?2:0.7} onClick={()=>onSelect(s.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(s.id);}}}><title>{tidy(s.name)} · {s.id} · {year}: {signed(a)} {unit(metric)}</title></circle>;})}<circle cx={x} cy={y} r="11" fill="none" stroke="#fff" strokeOpacity="0.55" pointerEvents="none"/><g pointerEvents="none"><rect x={Math.min(435,Math.max(8,x-82))} y={y>50?y-40:y+18} width="164" height="24" rx="4" fill="#07141f" stroke="#567080"/><text x={Math.min(435,Math.max(8,x-82))+82} y={y>50?y-24:y+34} fill="#eff7fc" fontSize="12" textAnchor="middle">{tidy(station.name)}</text></g></svg>;
}

function TimeChart({id,stationList,metric,year,setYear,start,anomalies=false}:{id:string;stationList:Station[];metric:Metric;year:number;setYear:(y:number)=>void;start:number;anomalies?:boolean}){
  const ref=useRef<HTMLDivElement>(null);const [width,setWidth]=useState(560);const gradient=useId().replaceAll(':','');
  useEffect(()=>{if(!ref.current)return;const observer=new ResizeObserver(([entry])=>setWidth(Math.max(280,entry.contentRect.width)));observer.observe(ref.current);return()=>observer.disconnect();},[]);
  const h=248,left=48,right=16,top=20,bottom=36;
  const getValue=(r:Annual|undefined)=>anomalies?anomaly(r,metric):r?.[metric]??null;
  const allValues=stationList.flatMap(s=>s.history.filter(r=>r.year>=start).map(getValue)).filter((v):v is number=>v!==null);
  let lo=allValues.length?Math.min(...allValues):0,hi=allValues.length?Math.max(...allValues):1;
  if(anomalies){hi=Math.max(Math.abs(lo),Math.abs(hi),metric==='temp'?1:100)*1.1;lo=-hi;}else{const pad=Math.max((hi-lo)*0.14,metric==='temp'?0.5:20);lo=metric==='rain'?Math.max(0,lo-pad):lo-pad;hi+=pad;}
  const xx=(y:number)=>left+(y-start)/(LAST_YEAR-start)*(width-left-right), yy=(v:number)=>top+(hi-v)/(hi-lo)*(h-top-bottom);
  const ticks=Array.from({length:4},(_,i)=>lo+(hi-lo)*i/3);
  const yearTicks=Array.from(new Set([start,...[1980,2000,2020].filter(y=>y>start&&y<2020+(start===2011?0:1)),LAST_YEAR])).filter((y,i,a)=>y===start||y===LAST_YEAR||y-start>4&&LAST_YEAR-y>4);
  function line(s:Station){let pen=false;return years.filter(y=>y>=start).map(y=>{const v=getValue(annual(s,y));if(v===null){pen=false;return '';}const command=pen?'L':'M';pen=true;return `${command}${xx(y)},${yy(v)}`;}).join(' ');}
  const active=getValue(annual(stationList[0],year));
  return <div ref={ref} className="time-chart"><svg id={id} width="100%" height={h} viewBox={`0 0 ${width} ${h}`} role="group" aria-label={`${anomalies?'Anomaly':'Annual'} ${metric==='temp'?'temperature':'precipitation'} chart. Arrow keys change year.`} tabIndex={0} onKeyDown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();setYear(Math.min(LAST_YEAR,Math.max(start,year+(e.key==='ArrowLeft'?-1:1))));}}} onPointerMove={e=>{if(e.pointerType==='touch'&&e.buttons===0)return;const rect=e.currentTarget.getBoundingClientRect();const px=(e.clientX-rect.left)/rect.width*width;setYear(Math.max(start,Math.min(LAST_YEAR,Math.round(start+(px-left)/(width-left-right)*(LAST_YEAR-start)))));}}>
    <defs><linearGradient id={gradient} x1="0" x2="1" y1="0" y2="0"><stop stopColor="#55bfe1"/><stop offset="0.55" stopColor="#7addc8"/><stop offset="1" stopColor="#ffab70"/></linearGradient></defs>
    {ticks.map(v=><g key={v}><line x1={left} x2={width-right} y1={yy(v)} y2={yy(v)} stroke="#293b4b" strokeDasharray="3 5"/><text x={left-8} y={yy(v)+4} textAnchor="end" fill="#93a9b9" fontSize="12">{fmt(v,metric==='temp'?1:0)}</text></g>)}
    {yearTicks.map(y=><text key={y} x={xx(y)} y={h-12} textAnchor="middle" fill="#93a9b9" fontSize="12">{y}</text>)}
    {anomalies?<><line x1={left} x2={width-right} y1={yy(0)} y2={yy(0)} stroke="#79909f"/>{years.filter(y=>y>=start).map(y=>{const v=getValue(annual(stationList[0],y));return v===null?null:<rect key={y} x={xx(y)-Math.max(1.5,(width-left-right)/(LAST_YEAR+1-start)*0.34)} y={Math.min(yy(v),yy(0))} width={Math.max(3,(width-left-right)/(LAST_YEAR+1-start)*0.68)} height={Math.max(1,Math.abs(yy(v)-yy(0)))} rx="1" fill={v>=0?'#f39b77':'#61b7e4'} opacity={y===year?1:0.8}><title>{y}: {signed(v)} {unit(metric)}</title></rect>;})}</>:stationList.map((s,i)=><g key={s.id}><path d={line(s)} fill="none" stroke={stationList.length===1?`url(#${gradient})`:colors[i]} strokeWidth="2.4" strokeLinejoin="round"/>{s.history.filter(r=>r.year>=start&&getValue(r)!==null).map(r=><circle key={r.year} cx={xx(r.year)} cy={yy(getValue(r)!)} r={r.year===year?4:1.6} fill={stationList.length===1?'#97decc':colors[i]}><title>{tidy(s.name)} · {r.year}: {fmt(getValue(r))} {unit(metric)}</title></circle>)}</g>)}
    <line x1={xx(year)} x2={xx(year)} y1={top} y2={h-bottom} stroke="#d9e5ed" strokeOpacity="0.6" strokeDasharray="3 4"/>
    <rect x={Math.min(width-140,Math.max(left,xx(year)-55))} y={2} width="124" height="22" rx="4" fill="#263d4d"/><text x={Math.min(width-140,Math.max(left,xx(year)-55))+62} y="17" fill="#f0f5f8" fontSize="12" textAnchor="middle">{year} · {fmt(active)} {unit(metric)}</text>
    {!allValues.length&&<text x={width/2} y={h/2} fill="#becbd4" fontSize="14" textAnchor="middle">No eligible annual values in this period</text>}
  </svg></div>;
}

function Heatmap({station,metric,year,setYear,start,compact=false}:{station:Station;metric:Metric;year:number;setYear:(y:number)=>void;start:number;compact?:boolean}){
  const decades=Array.from({length:Math.floor((LAST_YEAR-1960)/10)+1},(_,i)=>1960+i*10).filter(d=>d+9>=start);
  return <div className={'heatmap '+(compact?'compact':'')}><div className="heatmap-head"><span>Decade</span><div>{Array.from({length:10},(_,i)=><span key={i}>{compact?i:`’0${i}`}</span>)}</div></div>{decades.map(d=><div className="heatmap-row" key={d}><span>{d}s</span><div>{Array.from({length:10},(_,i)=>{const y=d+i;const v=anomaly(annual(station,y),metric);return y<start||y>LAST_YEAR?<span key={y} className="heat-spacer"/>:<button key={y} aria-label={`${y}: ${v==null?'no eligible anomaly':signed(v)+' '+unit(metric)}`} aria-pressed={y===year} title={`${y}: ${signed(v)} ${unit(metric)}`} className={y===year?'chosen':''} style={{background:anomalyColor(v,metric),color:v===null?'#b8c4cf':'#12232d'}} onClick={()=>setYear(y)}>{compact?'':v==null?'—':signed(v)}</button>;})}</div></div>)}<div className="heatmap-legend"><span>{metric==='temp'?'Cooler':'Drier'}</span><i/><span>{metric==='temp'?'Warmer':'Wetter'}</span></div>{!compact&&<p className="caption" aria-live="polite">{year}: {signed(anomaly(annual(station,year),metric))} {unit(metric)} departure from the 1991–2020 normal</p>}</div>;
}

function ChartSave({target,title,setNotice}:{target:string;title:string;setNotice:(s:string)=>void}){
  const [busy,setBusy]=useState(false);
  async function save(){
    setBusy(true);
    try{
      const original=document.getElementById(target) as unknown as SVGSVGElement;
      const clone=original.cloneNode(true) as SVGSVGElement;
      inlineSVGTheme(original,clone);
      const themeStyle=getComputedStyle(document.documentElement);
      const exportInk=themeStyle.getPropertyValue('--ink').trim();
      const exportBackground=themeStyle.getPropertyValue('--panel').trim();
      const [,,w,h]=original.getAttribute('viewBox')!.split(' ').map(Number);
      clone.setAttribute('x','0');clone.setAttribute('y','52');clone.setAttribute('width',String(w));clone.setAttribute('height',String(h));
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width',String(w));svg.setAttribute('height',String(h+112));svg.setAttribute('viewBox',`0 0 ${w} ${h+112}`);
      const bg=document.createElementNS(svg.namespaceURI,'rect');bg.setAttribute('width','100%');bg.setAttribute('height','100%');bg.setAttribute('fill',exportBackground);svg.append(bg);
      const text=(content:string,y:number,size:number)=>{const node=document.createElementNS(svg.namespaceURI,'text');node.setAttribute('x','18');node.setAttribute('y',String(y));node.setAttribute('fill',exportInk);node.setAttribute('font-family','Arial,sans-serif');node.setAttribute('font-size',String(size));node.textContent=content;svg.append(node);};
      text('Romanian Climate Explorer',22,15);text(title,43,Math.max(10,Math.min(12,(w-36)/(title.length*0.58))));svg.append(clone);text('© WxProbs · Observations: ANM',h+80,13);text(`ANM snapshot ${snapshot.snapshotDate} · 1991–2020 anomaly baseline`,h+100,11);
      const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'});const src=URL.createObjectURL(blob);
      try{const img=new Image();await new Promise<void>((resolve,reject)=>{img.onload=()=>resolve();img.onerror=()=>reject(Error('Could not render chart'));img.src=src;});const canvas=document.createElement('canvas');canvas.width=Math.round(w*2);canvas.height=(h+112)*2;const context=canvas.getContext('2d')!;context.scale(2,2);context.drawImage(img,0,0,w,h+112);const png=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('Could not save PNG')),'image/png'));download(png,'WxProbs-climate-chart.png');setNotice('Chart saved as PNG with © WxProbs.');}finally{URL.revokeObjectURL(src);}
    }catch(e){setNotice(e instanceof Error?e.message:'Chart export failed.');}finally{setBusy(false);}
  }
  return <button className="icon-button" aria-label="Save chart as PNG" title="Save PNG · © WxProbs" onClick={save} disabled={busy}><ArrowDownToLine size={17}/></button>;
}

createRoot(document.getElementById('root')!).render(<App/>);
