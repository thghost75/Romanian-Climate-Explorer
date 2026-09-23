
export function mountArchive(host,onChange){
 const controller=new AbortController();
 let disposed=false;
const E=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,d=1)=>v===null||v===undefined||!Number.isFinite(Number(v))?"No data":Number(v).toLocaleString("en-GB",{maximumFractionDigits:d,minimumFractionDigits:d});
const unit={tmean_c:"°C",tmin_c:"°C",tmax_c:"°C",precip_mm:"mm",wind_mean_ms:"m/s",pressure_msl_hpa:"hPa"};
const names={tmean_c:"Mean temperature",tmin_c:"Minimum temperature",tmax_c:"Maximum temperature",precip_mm:"Precipitation",wind_mean_ms:"Mean wind",pressure_msl_hpa:"Sea-level pressure"};
const recordNames={highest_tmax:"Highest Tmax",lowest_tmin:"Lowest Tmin",lowest_tmax:"Lowest Tmax",highest_tmin:"Highest Tmin",highest_tmean:"Highest Tmean",lowest_tmean:"Lowest Tmean",highest_precip:"Wettest day",highest_mean_wind:"Highest mean wind",highest_pressure:"Highest pressure",lowest_pressure:"Lowest pressure"};
const recordVars={highest_tmax:"tmax_c",lowest_tmin:"tmin_c",lowest_tmax:"tmax_c",highest_tmin:"tmin_c",highest_tmean:"tmean_c",lowest_tmean:"tmean_c",highest_precip:"precip_mm",highest_mean_wind:"wind_mean_ms",highest_pressure:"pressure_msl_hpa",lowest_pressure:"pressure_msl_hpa"};
const today=new Date(),state={station:"0-20000-0-15085",normal:"1991-2020",month:today.getMonth()+1,day:today.getDate(),year:today.getFullYear()-1,tab:"overview",recordScope:"day",mode:"stations",catalogue:[],boundary:null};
let serial=0,mapSerial=0;const cache=new Map(),API="";
async function api(endpoint,params={}){
 const url=API+"/api/climate/"+endpoint+"?"+new URLSearchParams(params);
 if(cache.has(url))return cache.get(url);
 const response=await fetch(url,{signal:controller.signal}),data=await response.json();if(!response.ok)throw Error(data.error||"Climate request failed");
 cache.set(url,data);if(cache.size>64)cache.delete(cache.keys().next().value);return data;
}
const params=()=>({station:state.station,normal:state.normal,month:state.month,day:state.day,year:state.year});
const sample=s=>!s||!s.sample_count?"No data":!s.eligible?"Insufficient climatological sample · n="+s.sample_count:"n="+s.sample_count+(s.expected_count?" / "+s.expected_count+" years":"");
function card(label,value,units="",note="",variable=""){return '<div class="ce-card" data-variable="'+E(variable)+'"><div class="ce-muted ce-small">'+E(label)+'</div><div class="ce-value">'+E(value)+(units&&value!=="No data"?' <small>'+E(units)+'</small>':"")+'</div><div class="ce-small ce-muted">'+E(note)+'</div></div>';}
function normCard(v,s){return card(names[v],fmt(s?.eligible?s.mean:null),unit[v],sample(s),v);}
function panel(title,html){return '<section class="ce-panel"><h3>'+E(title)+'</h3>'+html+'</section>';}
function warn(r){return r?.needs_verification||r?.verification_notes?.length||r?.flagged_dates?.length?'<span class="ce-badge" title="Original source flags or a historical verification note apply; inspect details.">Verify observation</span>':"";}
function failure(node,error){node.innerHTML='<div class="ce-error" role="alert">'+E(error.message)+'</div>';}
function csv(filename,headers,rows){
 const cell=x=>{let s=typeof x==="object"?JSON.stringify(x):String(x??"");if(typeof x==="string"&&/^[=+\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
 const blob=new Blob(["\ufeff"+[headers,...rows].map(r=>r.map(cell).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});
 const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
function table(headers,rows){return '<div class="ce-table-wrap"><table class="ce-table"><thead><tr>'+headers.map(h=>"<th>"+E(h)+"</th>").join("")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+r.map(c=>"<td>"+c+"</td>").join("")+"</tr>").join("")+"</tbody></table></div>";}
function chart(title,labels,series,units,context=""){
 const w=900,h=245,L=58,R=18,T=16,B=40,all=series.flatMap(s=>s.values).filter(v=>v!==null&&v!==undefined&&Number.isFinite(v));
 if(!all.length)return panel(title,'<p class="ce-muted">No data or insufficient climatological sample.</p>');
 let lo=Math.min(...all),hi=Math.max(...all),pad=(hi-lo||2)*.12;lo=units==="mm"?Math.max(0,lo-pad):lo-pad;hi+=pad;
 const x=i=>L+i*(w-L-R)/Math.max(1,labels.length-1),y=v=>T+(hi-v)/(hi-lo)*(h-T-B);
 let svg='<svg class="ce-chart" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+E(title+' in '+units)+'">';
 for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4;svg+='<line class="ce-axis" x1="'+L+'" y1="'+y(v)+'" x2="'+(w-R)+'" y2="'+y(v)+'"/><text x="'+(L-8)+'" y="'+(y(v)+4)+'" text-anchor="end">'+E(fmt(v))+'</text>';}
 const step=Math.max(1,Math.ceil(labels.length/12));
 labels.forEach((label,i)=>{if(i%step===0||i===labels.length-1)svg+='<text x="'+x(i)+'" y="'+(h-15)+'" text-anchor="middle">'+E(label)+'</text>';});
 series.forEach(s=>{
  let path="",active=false;s.values.forEach((v,i)=>{if(v===null||v===undefined||!Number.isFinite(v)){active=false;return;}path+=(active?" L":" M")+x(i)+","+y(v);active=true;});
  svg+='<path d="'+path+'" stroke="'+s.color+'" fill="none" stroke-width="2.4"/>';
  s.values.forEach((v,i)=>{if(v!==null&&v!==undefined&&Number.isFinite(v))svg+='<circle cx="'+x(i)+'" cy="'+y(v)+'" r="'+(labels.length>50?2:4)+'" fill="'+s.color+'"><title>'+E(labels[i]+': '+s.name+' '+fmt(v)+' '+units)+'</title></circle>';});
 });svg+="</svg>";
 const legend='<div class="ce-legend">'+series.map(s=>'<span><i class="ce-dot" style="background:'+s.color+'"></i>'+E(s.name)+'</span>').join("")+'<span class="ce-muted">'+E(units)+' · gaps indicate unavailable values</span></div>';
 const station=state.catalogue.find(s=>s.station_id===state.station);
 const caption=(station?.station_name||state.station)+" · "+state.station+" · Normal "+state.normal+
  (context?" · "+context:state.tab==="history"?" · Year "+state.year:state.tab==="overview"?" · Calendar day "+String(state.month).padStart(2,"0")+"-"+String(state.day).padStart(2,"0"):"");
 return '<section class="ce-panel ce-chart-panel" data-export-context="'+E(caption)+'" data-export-name="'+E(state.station+"-"+title+(context?"-"+context:""))+'"><div class="ce-heading"><h3>'+E(title)+'</h3><div class="ce-chart-actions"><button type="button" data-chart-save="png" aria-label="'+E("Save "+title+" as PNG")+'">Save PNG</button> <button type="button" data-chart-save="svg" aria-label="'+E("Save "+title+" as SVG")+'">Save SVG</button></div></div>'+legend+svg+'<div class="ce-export-status ce-small" role="status"></div><details><summary>View chart data</summary>'+table(["Date",...series.map(s=>s.name+" ("+units+")")],labels.map((l,i)=>[E(l),...series.map(s=>E(fmt(s.values[i])))]))+'</details></section>';
}
// Build a self-contained image: titles, legend, attribution and chart styles travel with it.
async function saveChart(panel,format){
 const themeStyle=getComputedStyle(document.documentElement);
 const exportInk=themeStyle.getPropertyValue('--ink').trim();
 const exportMuted=themeStyle.getPropertyValue('--muted').trim();
 const exportBg=themeStyle.getPropertyValue('--panel').trim();
 const source=panel.querySelector("svg.ce-chart"),ns="http://www.w3.org/2000/svg";
 const svg=document.createElementNS(ns,"svg"),width=960,plotHeight=source.viewBox.baseVal.height;
 const add=(tag,attrs,text,parent=svg)=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;parent.append(el);return el;};
 let y=32;
 const textLines=(text,size,color)=>{
  // Wrap using the same font metrics as the image, including long station names.
  const measure=document.createElement("canvas").getContext("2d");measure.font=size+"px Arial";
  let line="";
  for(const word of text.split(/\s+/)){const next=line?line+" "+word:word;if(line&&measure.measureText(next).width>width-60){add("text",{x:30,y,"font-family":"Arial","font-size":size,fill:color},line);y+=size+7;line=word;}else line=next;}
  if(line){add("text",{x:30,y,"font-family":"Arial","font-size":size,fill:color},line);y+=size+7;}
 };
 textLines(panel.querySelector("h3").textContent,22,exportInk);
 textLines(panel.dataset.exportContext,13,exportMuted);
 for(const item of panel.querySelectorAll(".ce-legend > span")){
  const dot=item.querySelector(".ce-dot");
  if(dot){add("circle",{cx:35,cy:y-4,r:4,fill:getComputedStyle(dot).backgroundColor});add("text",{x:48,y,"font-family":"Arial","font-size":13,fill:exportMuted},item.textContent);y+=21;}
  else textLines(item.textContent,12,exportMuted);
 }
 y+=8;
 const plot=source.cloneNode(true);
 // External CSS is unavailable when an SVG is opened on its own or rasterized.
 const originals=source.querySelectorAll("text,line"),copies=plot.querySelectorAll("text,line");
 originals.forEach((el,i)=>{const style=getComputedStyle(el);for(const key of ["fill","stroke","stroke-width","font-family","font-size","font-weight"])copies[i].setAttribute(key,style.getPropertyValue(key));});
 plot.removeAttribute("class");plot.setAttribute("x","30");plot.setAttribute("y",String(y));plot.setAttribute("width","900");plot.setAttribute("height",String(plotHeight));svg.append(plot);
 y+=plotHeight+25;
 textLines("Source: ANM / odp.meteoromania.ro · Eligible observations only; missing values remain gaps.",12,exportMuted);
 if(panel.dataset.exportName.includes("Cumulative rainfall"))textLines("Observed rainfall is a subtotal when coverage is incomplete. Missing daily normals stop the reference accumulation.",12,exportMuted);
 y+=6;
 textLines("© WxProbs",14,exportInk);
 const height=y+12;svg.setAttribute("xmlns",ns);svg.setAttribute("viewBox","0 0 "+width+" "+height);svg.setAttribute("width",width);svg.setAttribute("height",height);
 const background=document.createElementNS(ns,"rect");background.setAttribute("width","100%");background.setAttribute("height","100%");background.setAttribute("fill",exportBg);svg.prepend(background);
 const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:"image/svg+xml;charset=utf-8"});
 let output=blob;
 if(format==="png"){
  const image=new Image(),url=URL.createObjectURL(blob);
  try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error("Image rendering failed"));image.src=url;});
   const canvas=document.createElement("canvas");canvas.width=width*2;canvas.height=height*2;canvas.getContext("2d").drawImage(image,0,0,canvas.width,canvas.height);
   output=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));if(!output)throw Error("PNG export failed");
  }finally{URL.revokeObjectURL(url);}
 }
 const filename=panel.dataset.exportName.normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-zA-Z0-9.-]+/g,"-").replace(/-+$/,"").slice(0,180);
 const url=URL.createObjectURL(output),link=document.createElement("a");link.href=url;link.download=filename+"."+format;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
const saveHandler=async event=>{
 const button=event.target.closest("[data-chart-save]");if(!button||!host.contains(button))return;
 const panel=button.closest(".ce-chart-panel"),status=panel.querySelector(".ce-export-status");
 button.disabled=true;status.textContent="Preparing image…";
 try{await saveChart(panel,button.dataset.chartSave);status.textContent=button.dataset.chartSave.toUpperCase()+" chart downloaded.";}
 catch(error){status.textContent="Unable to save this image. Please try again or choose the other format.";console.error(error);}
 finally{button.disabled=false;}
};
host.addEventListener("click",saveHandler);

function modal(title,body){
 const previous=document.activeElement,wrap=document.createElement("div");wrap.className="ce-modal archive-modal";wrap.innerHTML='<section class="ce-modal-content" role="dialog" aria-modal="true" aria-label="'+E(title)+'"><button class="ce-modal-close" aria-label="Close dialog">Close ×</button><h3>'+E(title)+'</h3><div class="ce-modal-body">'+body+"</div></section>";document.body.append(wrap);
 const close=()=>{wrap.remove();previous?.focus();};wrap.querySelector("button").onclick=close;wrap.onclick=e=>{if(e.target===wrap)close();};
 wrap.onkeydown=e=>{if(e.key==="Escape")close();if(e.key==="Tab"){const f=[...wrap.querySelectorAll('button,a,input,select,summary,[tabindex="0"]')];if(e.shiftKey&&document.activeElement===f[0]){e.preventDefault();f.at(-1).focus();}else if(!e.shiftKey&&document.activeElement===f.at(-1)){e.preventDefault();f[0].focus();}}};wrap.querySelector("button").focus();return wrap.querySelector(".ce-modal-body");
}
function recordDetails(r,label){
 const rows=(r.observations||[]).map(o=>[E(o.date),E(fmt(o.value)),o.quality_flags?.length?E(JSON.stringify(o.quality_flags)):"None",E((o.verification_notes||[]).map(n=>n.review_reason).join("; ")||"None"),E(o.source_member+":"+o.source_line)]);
 modal(label+" · all tied dates",'<p>Variable-level QC applies. Flags on other variables remain visible without automatically invalidating this value.</p>'+table(["Date","Value","Original flags","Verification notes","Source"],rows));
}
async function eventDetails(r){
 const node=modal("Event observations",'<p>Loading observations…</p>');
 try{const d=await api("event-context",{station:r.station_id||state.station,start:r.start_date||r.date,end:r.end_date||r.date});
 const rows=d.observations.map(o=>[E(o.date),...Object.keys(unit).map(v=>E(fmt(o[v]))+(o.excluded_variables[v]?' <span class="ce-badge" title="'+E(o.excluded_variables[v])+'">Excluded</span>':"")),o.precip_trace?"Trace":o.precip_mm===0?"Dry":"",o.quality_flags.length||o.verification_notes.length?'<details><summary>Verification details</summary><p>'+E(JSON.stringify(o.quality_flags))+'</p><p>'+E(o.verification_notes.map(n=>n.review_reason).join(" "))+'</p></details>':"",E(o.source_member+":"+o.source_line)]);
 node.innerHTML='<p class="ce-muted">Two days before and after. '+E(d.note)+'</p>'+(d.missing_dates?.length?'<p class="ce-warning">No source rows for: '+E(d.missing_dates.join(', '))+'</p>':'')+table(["Date",...Object.keys(unit).map(v=>names[v]+" ("+unit[v]+")"),"Rain state","Quality","Source"],rows)+'<p><button id="ce-context-export">Export observations CSV</button></p>';
 node.querySelector("#ce-context-export").onclick=()=>csv("event-observations.csv",["date",...Object.keys(unit),"trace","original_flags","excluded_variables","verification_notes"],d.observations.map(o=>[o.date,...Object.keys(unit).map(v=>o[v]),o.precip_trace,o.quality_flags,o.excluded_variables,o.verification_notes]));
 }catch(e){failure(node,e);}
}
const help='<details class="ce-help"><summary>How to read these climate statistics</summary><dl>'+
'<dt>Climate normal</dt><dd>A 30-year reference period. Each statistic reports its eligible sample; at least 80% of expected years are required for daily normals.</dd>'+
'<dt>Percentile</dt><dd>The position within comparable historical values. P90 is a threshold near the warmest 10%; ties and small samples affect the exact proportion.</dd>'+
'<dt>Anomaly</dt><dd>Difference from the stated normal. Historical annual anomalies use 1991–2020. The selected normal controls daily and monthly climatology.</dd>'+
'<dt>Trace precipitation</dt><dd>Precipitation below a measurable amount. Stored as 0 mm plus a trace flag; distinct from a completely dry day. Measurable rain is greater than 0 mm.</dd>'+
'<dt>Heat / cold events</dt><dd>Year-round relative candidates: at least three consecutive Tmax ≥ P90 or Tmin ≤ P10 days, using a ±7-day calendar window and 1991–2020 baseline. Not certified severe-weather or health events.</dd>'+
'<dt>Dry / wet periods</dt><dd>Daily rain below 1 mm / at least 1 mm. Missing or ineligible data break runs; runs are clipped at calendar-year boundaries, matching Phase 3 indices.</dd>'+
'<dt>Completeness & QC</dt><dd>Missing values stay missing. Rainfall totals require complete months/years; observed partial totals are labelled. Original flags and verification notes are in record/event details. No relocations are inferred.</dd>'+
'<dt>February 29</dt><dd>Actual leap-year observations only, with its own smaller expected sample.</dd></dl></details>';

 const $=id=>host.querySelector("#"+id);
function stationTitle(){
 const s=state.catalogue.find(s=>s.station_id===state.station);if(!s)return;
 $("ce-station-title").innerHTML='<div class="ce-heading"><div><div class="ce-eyebrow">'+E(s.station_id)+'</div><h2>'+E(s.station_name||"Station name unavailable")+'</h2><p class="ce-small ce-muted">'+(s.has_coordinates?E(fmt(s.latitude,3)+"°N · "+fmt(s.longitude,3)+"°E"):"Official coordinates unavailable")+" · Elevation "+(s.elevation_m===null?"unavailable":E(fmt(s.elevation_m,0))+" m")+'</p></div><div class="ce-small ce-station-meta">'+E(s.first_observation)+" → "+E(s.last_observation)+'<br>'+E(fmt(s.observation_days,0))+' observed days · '+E(fmt(s.completeness_percent))+'% coverage '+(s.incomplete?'<span class="ce-badge">Incomplete record</span>':"")+'<br><strong>Selected normal '+E(state.normal)+'</strong><br><button id="ce-quality">Data quality details</button></div></div>';
 $("ce-quality").onclick=async()=>{const target=modal("Station data quality","Loading quality counts…");try{const q=await api("quality",{station:state.station});target.innerHTML='<p>'+E(q.policy)+'</p>'+table(["Variable","Eligible values","Missing","Excluded values"],q.variables.map(v=>[E(names[v.variable]),E(v.eligible_count),E(v.missing_count),E(v.excluded_count)]))+(q.verification_notes.length?q.verification_notes.map(n=>'<p class="ce-warning">'+E(n.start_date+' → '+n.end_date+': '+n.review_reason)+'</p>').join(''):'<p>No additional historical verification note has been recorded. This is not a certification of all source measurements.</p>');}catch(e){failure(target,e);}};
}
async function renderTab(){
 const request=++serial;stationTitle();host.querySelectorAll("[data-tab]").forEach(b=>{b.classList.toggle("active",b.dataset.tab===state.tab);b.setAttribute("aria-current",b.dataset.tab===state.tab?"page":"false");});
 const content=$("ce-content");content.dataset.ready="false";content.innerHTML='<p class="ce-status" role="status">Loading '+E(state.tab)+'…</p>';
 try{
 const endpoint={overview:"overview",records:"records",temperature:"temperature",rainfall:"rainfall",extremes:"events",history:"history"}[state.tab];
 const extra=state.tab==="extremes"?{kind:"heatwave",start:(state.year-4)+"-01-01",end:state.year+"-12-31"}:state.tab==="records"?{scope:state.recordScope}:{};
 const data=await api(endpoint,{...params(),...extra});if(request!==serial)return;
 await ({overview:renderOverview,records:renderRecords,temperature:renderTemperature,rainfall:renderRainfall,extremes:renderExtremes,history:renderHistory}[state.tab])(content,data);
 if(request===serial){Object.assign(content.dataset,{ready:"true",station:state.station,normal:state.normal,tab:state.tab,year:String(state.year)});}
 }catch(e){if(request===serial)failure(content,e);}
}

function renderOverview(node,d){
 const vars=d.daily.variables,records=d.records.records,p=vars.precip_mm,percentiles=["p10","p25","p50","p75","p90","p95","p99"];
 node.innerHTML='<div class="ce-controls ce-daily-callout"><button id="ce-open-daily">Explore daily weather · '+state.year+'</button><span class="ce-muted ce-small">Temperature ranges, rainfall, anomalies and image downloads. Choose any available year in History.</span></div>'+panel("Normal conditions · "+d.daily.calendar_day,'<div class="ce-grid">'+["tmean_c","tmin_c","tmax_c","precip_mm","wind_mean_ms","pressure_msl_hpa"].map(v=>normCard(v,vars[v])).join("")+"</div>")+
 panel("Daily temperature distributions",table(["Statistic",...percentiles.map(p=>p.toUpperCase()),"Eligible sample"],["tmax_c","tmean_c","tmin_c"].map(v=>[E(names[v]),...percentiles.map(p=>E(fmt(vars[v]?.eligible?vars[v][p]:null))+" °C"),E(sample(vars[v]))])))+
 chart("Where temperatures fall",percentiles.map(p=>p.toUpperCase()),[["tmax_c","#cb6649"],["tmean_c","#087c98"],["tmin_c","#6c80bf"]].map(([v,color])=>({name:names[v],color,values:percentiles.map(p=>vars[v]?.eligible?vars[v][p]:null)})),"°C")+
 panel("Historical records on this calendar day",'<div class="ce-grid">'+["highest_tmax","lowest_tmin","highest_precip"].map(k=>{const r=records[k];return '<div>'+card(recordNames[k],fmt(r?.value),unit[recordVars[k]],r?.dates?.join(" · ")||"No data")+(r?warn(r)+' <button data-record="'+k+'">Inspect dates & QC</button>':"")+"</div>";}).join("")+"</div>")+
 panel("Rain occurrence",'<div class="ce-grid">'+card("Measurable rain (>0 mm)",fmt(p?.eligible&&p.sample_count?100*p.measurable_rain_days/p.sample_count:null),"%",sample(p))+card("Trace reports",p?.eligible?fmt(p.trace_days,0):"No data","days",sample(p))+card("Completely dry",p?.eligible?fmt(p.dry_days,0):"No data","days",sample(p))+"</div>")+
 '<p class="ce-muted ce-small">Historical observations and climate normals for the selected ANM station. Gaps and quality flags are retained.</p>';
 node.querySelector("#ce-open-daily").onclick=()=>{onChange({tab:"history"});};
 node.querySelectorAll("[data-record]").forEach(b=>b.onclick=()=>recordDetails(records[b.dataset.record],recordNames[b.dataset.record]));
}
function renderRecords(node,d){
 const station=state.catalogue.find(s=>s.station_id===state.station);
 const yearly=['year','month-year'].includes(state.recordScope);
 const scopes=[['day','Calendar day · all years'],['month','Calendar month · all years'],['month-year','Month in a selected year'],['year','Selected year'],['all','All-time station records']];
 node.innerHTML='<div class="ce-controls"><label>Record scope<select id="ce-record-scope" aria-label="Record scope">'+scopes.map(([value,label])=>'<option value="'+value+'"'+(value===state.recordScope?' selected':'')+'>'+label+'</option>').join('')+'</select></label>'+
 (yearly?'<label>Record year<input id="ce-record-year" type="number" min="'+station.first_year+'" max="'+station.last_year+'" value="'+state.year+'"></label><button id="ce-record-load">View records</button>':'')+
 '<button id="ce-record-export">Export records CSV</button></div><div id="ce-record-table"></div>';
 node.querySelector("#ce-record-table").innerHTML=panel("Historical records · "+d.period_label,'<p class="ce-small ce-muted">'+E(d.qc_policy)+'</p><p class="ce-small ce-muted">Lowest Tmax is the coldest daily maximum; highest Tmin is the warmest daily minimum. Values are daily extremes within the selected period.</p>'+table(["Record","Value","Sample (days)","All tied dates","Quality"],Object.entries(d.records).map(([k,r])=>[E(recordNames[k]),E(r.value==null?'No data':fmt(r.value)+' '+unit[recordVars[k]]),E(r.sample_count),r.dates.length?'<button data-record="'+k+'">'+r.dates.length+' date'+(r.dates.length===1?'':'s')+' · inspect</button><div class="ce-muted">'+E(r.dates.slice(0,2).join(' · '))+(r.dates.length>2?' …':'')+'</div>':'—',r.value==null?'No eligible observations':warn(r)||'Eligible'])));
 node.querySelectorAll('[data-record]').forEach(b=>b.onclick=()=>recordDetails(d.records[b.dataset.record],recordNames[b.dataset.record]));
 node.querySelector('#ce-record-scope').onchange=e=>{state.recordScope=e.target.value;void renderTab();};
 if(yearly)node.querySelector('#ce-record-load').onclick=()=>{const y=Number(node.querySelector('#ce-record-year').value);if(!Number.isInteger(y)||y<station.first_year||y>station.last_year){modal('Choose a year','Choose a year between '+station.first_year+' and '+station.last_year+'.');return;}if(y!==state.year)onChange({year:y});};
 node.querySelector('#ce-record-export').onclick=()=>csv('station-records.csv',['station','scope','period','year','month','record','value','unit','sample_days','dates','verification','observation_details'],Object.entries(d.records).map(([k,r])=>[state.station,d.scope,d.period_label,d.year,d.month,k,r.value,unit[recordVars[k]],r.sample_count,r.dates,r.needs_verification,r.observations]));
}
const colors={tmax_c:"#ca6447",tmean_c:"#0b8098",tmin_c:"#7285c0"};
function renderTemperature(node,d){
 const labels=d.monthly_normals.map(m=>new Date(2000,m.month-1,1).toLocaleString("en-GB",{month:"short"}));
 node.innerHTML=chart("Monthly temperature normals · "+state.normal,labels,["tmax_c","tmean_c","tmin_c"].map(v=>({name:names[v],color:colors[v],values:d.monthly_normals.map(m=>m.variables?.[v]?.mean)})),"°C")+
 '<div class="ce-controls"><label>Annual series<select id="ce-temp-series"><option value="mean">Annual mean temperature</option><option value="anomaly">Anomaly vs 1991–2020</option></select></label><button id="ce-temp-export">Export annual series CSV</button><button id="ce-cycle-button">Show daily annual cycle</button></div><div id="ce-annual-chart"></div><div id="ce-daily-cycle"></div>'+
 panel("Monthly normal samples",table(["Month","Tmax °C","n years","Tmean °C","n years","Tmin °C","n years"],d.monthly_normals.map((m,i)=>[E(labels[i]),...["tmax_c","tmean_c","tmin_c"].flatMap(v=>[E(fmt(m.variables?.[v]?.mean)),E(sample(m.variables?.[v]))])])))+
 '<p class="ce-muted ce-small">Station observations have gaps and may reflect site/instrument changes. This chart alone is not a trend attribution.</p>';
 const draw=metric=>node.querySelector("#ce-annual-chart").innerHTML=chart(metric==="mean"?"Historical annual mean temperature":"Annual temperature anomaly · 1991–2020",d.annual.map(a=>String(a.year)),[{name:metric==="mean"?"Annual mean":"Annual anomaly",color:"#0b8098",values:d.annual.map(a=>a.variables.tmean_c[metric])}],"°C");
 draw("mean");node.querySelector("#ce-temp-series").onchange=e=>draw(e.target.value);
 node.querySelector("#ce-temp-export").onclick=()=>csv("annual-temperature.csv",["year","mean_c","anomaly_c_1991_2020","sample_days","eligible"],d.annual.map(a=>[a.year,a.variables.tmean_c.mean,a.variables.tmean_c.anomaly,a.variables.tmean_c.sample_count,a.variables.tmean_c.eligible]));
 node.querySelector("#ce-cycle-button").onclick=async e=>{e.target.disabled=true;const target=node.querySelector("#ce-daily-cycle");target.textContent="Loading daily cycle…";try{const data=await api("cycle",params());target.innerHTML=chart("Daily temperature cycle · "+state.normal,data.map(x=>x.calendar_day),["tmax_c","tmean_c","tmin_c"].map(v=>({name:names[v],color:colors[v],values:data.map(x=>x.variables[v]?.mean)})),"°C");}catch(e){failure(target,e);}};
}
async function renderRainfall(node,d){
 const n=serial,[daily,record]=await Promise.all([api("daily",params()),api("records",{...params(),scope:"all"})]);if(n!==serial)return;
 const p=daily.variables.precip_mm,r=record.records.highest_precip,months=d.monthly_normals;
 node.innerHTML=chart("Monthly precipitation normals · "+state.normal,months.map(m=>String(m.month)),[{name:"Normal monthly total",color:"#0b8098",values:months.map(m=>m.variables?.precip_mm?.mean)}],"mm")+
 chart("Historical annual precipitation",d.annual.map(a=>String(a.year)),[{name:"Complete annual total",color:"#0b8098",values:d.annual.map(a=>a.variables.precip_mm.total)}],"mm")+
 panel("Rainfall on "+daily.calendar_day,table(["At least","Historical probability","Eligible sample"],["0.1","1","5","10","20","30","50"].map(t=>["≥"+t+" mm",E(fmt(p?.eligible?100*p.probability_ge[t]:null))+" %",E(sample(p))]))+
 '<p class="ce-small ce-muted">Trace and completely dry days are included separately in the sample; neither meets ≥0.1 mm.</p>')+
 panel("Rain-day and trace frequency",table(["Month","Normal total mm","n years","Wet days ≥1 mm","Measurable >0 mm","Trace days","Dry days"],months.map(m=>{const v=m.variables?.precip_mm,a=v?.additional_metrics||{};return [E(m.month),E(fmt(v?.mean)),E(sample(v)),...["rain_days","measurable_rain_days","trace_days","dry_days"].map(k=>E(fmt(a[k]?.mean))+' <small>('+E(sample(a[k]))+')</small>')];})))+
 panel("Wettest historical day",(r?card("Daily precipitation",fmt(r.value),"mm",r.dates.join(" · "))+warn(r)+'<button id="ce-wettest-details">Inspect all dates & QC</button>':"No data"))+
 '<button id="ce-rain-export">Export annual precipitation CSV</button><p class="ce-small ce-muted">Incomplete annual totals are gaps. Partial observed totals are available in History and exported with explicit eligibility.</p>';
 if(r)node.querySelector("#ce-wettest-details").onclick=()=>recordDetails(r,"Wettest day");
 node.querySelector("#ce-rain-export").onclick=()=>csv("annual-precipitation.csv",["year","complete_total_mm","partial_observed_total_mm","sample_days","eligible"],d.annual.map(a=>[a.year,a.variables.precip_mm.total,a.variables.precip_mm.observed_total,a.variables.precip_mm.sample_count,a.variables.precip_mm.eligible]));
}
function renderExtremes(node,initial){
 node.innerHTML='<div class="ce-controls"><label>Event type<select id="ce-event-kind"><option value="heatwave">Heatwaves</option><option value="cold">Cold events</option><option value="rain">Extreme rainfall</option><option value="dry">Dry periods</option><option value="wet">Wet periods</option></select></label><label>Start date<input id="ce-start" type="date" value="'+(state.year-4)+'-01-01"></label><label>End date<input id="ce-end" type="date" value="'+state.year+'-12-31"></label><label>Rain threshold<select id="ce-threshold">'+[20,30,50,75,100].map(t=>'<option value="'+t+'" '+(t===50?"selected":"")+'>≥'+t+' mm</option>').join("")+'</select></label><button id="ce-event-load">Apply dates</button><label>Search these events<input id="ce-event-search" type="search" placeholder="Date, duration or value"></label><button id="ce-event-export">Export events CSV</button></div>'+
 '<p class="ce-small ce-muted">Heat/cold catalogues use 1991–2020, regardless of the normal selector. Date filtering returns overlapping events in full. Dry/wet periods follow calendar-year boundaries and accept up to 11 years per request.</p><div id="ce-event-table"></div>';
 const generation=serial;let current=initial,kind="heatwave",page=0,request=0,filtered=initial;
 function show(){
 const q=node.querySelector("#ce-event-search").value.toLowerCase();filtered=current.filter(r=>JSON.stringify(r).toLowerCase().includes(q));
 const rows=filtered.slice(page*50,(page+1)*50),rain=kind==="rain",spell=kind==="dry"||kind==="wet";
 const headers=rain?["Date","Rain mm","Percentile","Normal n","Quality","Details"]:spell?["Start","End","Days","Total mm","Trace days","Quality","Details"]:["Start","End","Days",kind==="cold"?"Maximum Tmin °C":"Maximum Tmax °C","Minimum °C","Mean anomaly °C","Peak percentile","Cumulative °C·days","Threshold n","Quality","Details"];
 const cells=rows.map((r,i)=>{
 const details='<button data-event="'+i+'">Surrounding days</button>';
 return rain?[E(r.date),E(fmt(r.precip_mm)),E(fmt(r.percentile)),E(r.normal_sample_count),warn(r),details]:spell?[E(r.start_date),E(r.end_date),E(r.duration),E(fmt(r.precip_mm)),E(r.trace_days),warn(r),details]:
 [E(r.start_date),E(r.end_date),E(r.duration),E(fmt(r.maximum_temperature)),E(fmt(r.minimum_temperature)),E(fmt(r.mean_temperature_anomaly)),E(fmt(r.peak_percentile)),E(fmt(r.cumulative_temperature_anomaly)),E(r.minimum_threshold_sample_count),warn(r),details];
 });
 node.querySelector("#ce-event-table").innerHTML=panel(filtered.length+" matching events",filtered.length?table(headers,cells)+'<div class="ce-controls"><button id="ce-prev" '+(page===0?"disabled":"")+'>Previous</button><span>Page '+(page+1)+" of "+Math.ceil(filtered.length/50)+'</span><button id="ce-next" '+((page+1)*50>=filtered.length?"disabled":"")+'>Next</button></div>':'<p>No events match. This does not establish complete observation coverage.</p>');
 node.querySelectorAll("[data-event]").forEach(b=>b.onclick=()=>eventDetails(rows[Number(b.dataset.event)]));
 const prev=node.querySelector("#ce-prev"),next=node.querySelector("#ce-next");if(prev)prev.onclick=()=>{page--;show();};if(next)next.onclick=()=>{page++;show();};
 }
 async function load(){
 const id=++request,k=node.querySelector("#ce-event-kind").value;
 node.querySelector("#ce-event-table").textContent="Loading events…";
 try{const result=await api("events",{...params(),kind:k,start:node.querySelector("#ce-start").value,end:node.querySelector("#ce-end").value,threshold:node.querySelector("#ce-threshold").value});if(id!==request||generation!==serial)return;current=result;kind=k;page=0;show();}catch(e){if(id===request&&generation===serial)failure(node.querySelector("#ce-event-table"),e);}
 }
 show();node.querySelector("#ce-event-load").onclick=load;node.querySelector("#ce-event-kind").onchange=load;node.querySelector("#ce-threshold").onchange=load;
 node.querySelector("#ce-event-search").oninput=()=>{page=0;show();};
 node.querySelector("#ce-event-export").onclick=()=>{const keys=[...new Set(filtered.flatMap(Object.keys))];csv(kind+"-events.csv",keys,filtered.map(r=>keys.map(k=>r[k])));};
}

async function renderHistory(node,d){
 const s=state.catalogue.find(s=>s.station_id===state.station),v=d.annual?.variables||{},idx=d.indices||{},months=d.monthly,labels=months.map(m=>String(m.month));
 node.innerHTML='<div class="ce-controls"><label>Historical year<input id="ce-history-year" type="number" min="'+s.first_year+'" max="'+s.last_year+'" value="'+state.year+'"></label><div class="ce-range"><span>'+s.first_year+'</span><input id="ce-history-slider" aria-label="Historical year" type="range" min="'+s.first_year+'" max="'+s.last_year+'" value="'+state.year+'"><span>'+s.last_year+'</span></div><button id="ce-history-load">View year</button><button id="ce-history-export">Export monthly comparison CSV</button></div>'+
 '<div id="ce-daily-year"><p role="status">Loading daily weather charts…</p></div>'+
 panel("Year "+d.year,'<div class="ce-grid">'+card("Annual mean temperature",fmt(v.tmean_c?.mean),"°C","n="+(v.tmean_c?.sample_count??0)+" days")+card("Temperature anomaly",fmt(v.tmean_c?.anomaly),"°C","Baseline 1991–2020")+card("Annual precipitation",fmt(v.precip_mm?.total),"mm",v.precip_mm?.eligible?"Complete annual total":"Incomplete · observed subtotal "+fmt(v.precip_mm?.observed_total)+" mm")+card("Absolute Tmax",fmt(v.tmax_c?.maximum),"°C","Available eligible days")+card("Absolute Tmin",fmt(v.tmin_c?.minimum),"°C","Available eligible days")+card("Wettest day",fmt(d.wettest_day.value),"mm",d.wettest_day.dates.join(" · "))+"</div>")+
 panel("Climate indices",table(["Index","Observed count","Sample days","Coverage"],Object.entries(idx).filter(([,x])=>typeof x==="object").map(([k,x])=>[E(k.replaceAll("_"," ")),E(x.count),E(x.sample_count+" / "+x.expected_days),x.complete?"Complete":'<span class="ce-badge">Incomplete · observed count</span>'])))+
 chart("Monthly mean temperature · "+d.year+" vs "+state.normal,labels,[{name:String(d.year),color:"#ca6447",values:months.map(m=>m.actual?.variables.tmean_c.mean)},{name:state.normal,color:"#0b8098",values:months.map(m=>m.normal?.tmean_c.mean)}],"°C")+
 chart("Monthly precipitation · "+d.year+" vs "+state.normal,labels,[{name:String(d.year),color:"#ca6447",values:months.map(m=>m.actual?.variables.precip_mm.total)},{name:state.normal,color:"#0b8098",values:months.map(m=>m.normal?.precip_mm.mean)}],"mm")+
 panel("Monthly values and samples",table(["Month","Tmean °C","Normal °C","Actual n days","Normal n years","Rain mm","Normal mm","Actual n days","Normal n years"],months.map(m=>[E(m.month),E(fmt(m.actual?.variables.tmean_c.mean)),E(fmt(m.normal?.tmean_c.mean)),E(m.actual?.variables.tmean_c.sample_count??0),E(sample(m.normal?.tmean_c)),E(fmt(m.actual?.variables.precip_mm.total)),E(fmt(m.normal?.precip_mm.mean)),E(m.actual?.variables.precip_mm.sample_count??0),E(sample(m.normal?.precip_mm))])))+
 '<p class="ce-small ce-muted">Phase 3 indices: frost Tmin &lt;0°C; ice Tmax &lt;0°C; summer/hot/very hot Tmax ≥25/30/35°C; tropical Tmin ≥20°C; heavy/very heavy rain ≥10/20 mm. Incomplete-year counts are observed lower bounds.</p>';
 node.querySelector("#ce-history-slider").oninput=e=>node.querySelector("#ce-history-year").value=e.target.value;
 node.querySelector("#ce-history-load").onclick=()=>{const y=Number(node.querySelector("#ce-history-year").value);if(!Number.isInteger(y)||y<s.first_year||y>s.last_year){modal("Choose a year","Choose a year between "+s.first_year+" and "+s.last_year+".");return;}onChange({year:y});};
 node.querySelector("#ce-history-export").onclick=()=>csv("monthly-history.csv",["year","month","normal_period","tmean_c","normal_tmean_c","tmean_sample_days","normal_tmean_sample_years","precip_mm","normal_precip_mm","precip_sample_days","normal_precip_sample_years"],months.map(m=>[d.year,m.month,state.normal,m.actual?.variables.tmean_c.mean,m.normal?.tmean_c.mean,m.actual?.variables.tmean_c.sample_count,m.normal?.tmean_c.sample_count,m.actual?.variables.precip_mm.total,m.normal?.precip_mm.mean,m.actual?.variables.precip_mm.sample_count,m.normal?.precip_mm.sample_count]));
 const request=serial;
 try {
  const daily=await api("daily-year",params());
  if(request!==serial)return;
  window.CLIMATE_DAILY_CHARTS.render(node.querySelector("#ce-daily-year"),daily,{E,fmt,chart,table,csv,modal});
 } catch(error) {if(request===serial)failure(node.querySelector("#ce-daily-year"),error);}

}
async function onDay(){
 const id=++serial,node=$("ce-on-day");node.textContent="Searching this calendar date…";
 try{const d=await api("on-this-day",{month:state.month,day:state.day});if(id!==serial)return;
 node.dataset.ready="true";
 let full=false;
 function show(){
 const groups=["highest_tmax","lowest_tmin","highest_precip"];
 const ordered=groups.flatMap(k=>{const rows=d.records.filter(r=>r.record_type===k).sort((a,b)=>k==="lowest_tmin"?a.value-b.value:b.value-a.value);return full?rows:rows.slice(0,10);});
 node.innerHTML='<div class="ce-heading"><div><div class="ce-eyebrow">On this day in Romania</div><h2>'+E(d.calendar_day)+'</h2><p class="ce-muted">'+(full?"All available station records":"Ten leading station records in each category")+' · all tied dates preserved</p></div><button id="ce-day-all">'+(full?"Show highlights":"Show complete results")+'</button></div>'+
 table(["Category","Station","Value","Dates","Quality","Explore"],ordered.map((r,i)=>[E(recordNames[r.record_type]),E(r.station_name||r.station_id)+'<div class="ce-muted">'+E(r.station_id)+"</div>",E(fmt(r.value)+" "+unit[recordVars[r.record_type]]),'<button data-day-record="'+i+'">'+E(r.dates.slice(0,2).join(" · "))+(r.dates.length>2?" · +"+(r.dates.length-2):"")+"</button>",warn(r)||"Eligible",'<button data-day-station="'+E(r.station_id)+'">Open station</button>']))+
 '<p><button id="ce-day-export">Export complete results CSV</button></p><p class="ce-muted ce-small">Records among available observations, not a complete or homogeneous national network. Missing station metadata is shown as the official ID.</p>';
 const rain=full?d.extreme_rainfall:d.extreme_rainfall.slice(0,10);
 node.innerHTML+=panel("Extreme rainfall on this date · ≥20 mm",table(["Station","Date","Rain mm","Quality","Details"],rain.map((r,i)=>[E(r.station_name||r.station_id),E(r.date),E(fmt(r.precip_mm)),warn(r),'<button data-day-rain="'+i+'">Surrounding days</button>'])))+'<p><button id="ce-day-rain-export">Export complete rainfall catalogue CSV</button></p>';
 node.querySelectorAll("[data-day-rain]").forEach(b=>b.onclick=()=>eventDetails(rain[Number(b.dataset.dayRain)]));
 node.querySelector("#ce-day-rain-export").onclick=()=>csv("on-this-day-rainfall.csv",["station","station_name","date","precip_mm","verification_notes","flagged_dates"],d.extreme_rainfall.map(r=>[r.station_id,r.station_name,r.date,r.precip_mm,r.verification_notes,r.flagged_dates]));
 node.querySelector("#ce-day-all").onclick=()=>{full=!full;show();};node.querySelectorAll("[data-day-record]").forEach(b=>b.onclick=()=>{const r=ordered[Number(b.dataset.dayRecord)];recordDetails(r,recordNames[r.record_type]);});
 node.querySelectorAll("[data-day-station]").forEach(b=>b.onclick=()=>{onChange({station:b.dataset.dayStation,tab:"records"});});
 node.querySelector("#ce-day-export").onclick=()=>csv("on-this-day.csv",["station","station_name","record","value","dates","verification"],d.records.map(r=>[r.station_id,r.station_name,r.record_type,r.value,r.dates,r.needs_verification]));
 }show();
 }catch(e){if(id===serial)failure(node,e);}
}

 return {
  async update(next){
   const request=++serial;
   Object.assign(state,next);
   host.innerHTML='<div id="ce-station-title"></div><div id="ce-content"></div><div id="ce-on-day"></div>'+help;
   $("ce-content").innerHTML='<p class="ce-status" role="status">Loading climate records…</p>';
   try{
    const catalogue=await api('stations');
    if(disposed||request!==serial)return;
    state.catalogue=catalogue;
    const selected=catalogue.find(s=>s.station_id===state.station);
    state.year=Math.max(selected.first_year,Math.min(selected.last_year,state.year));
    if(state.tab==='on-day'){
     $("ce-station-title").hidden=true;$("ce-content").hidden=true;
     await onDay();
    }else{
     $("ce-on-day").hidden=true;
     await renderTab();
    }
   }catch(error){if(!disposed&&request===serial)failure($("ce-content"),new Error('Climate records are temporarily unavailable. Please try again. '+error.message));}
  },
  destroy(){disposed=true;serial++;controller.abort();host.removeEventListener('click',saveHandler);document.querySelectorAll('.archive-modal').forEach(node=>node.remove());host.replaceChildren();}
 };
}
