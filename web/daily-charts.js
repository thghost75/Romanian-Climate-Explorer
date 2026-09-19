/* Bounded station/year visual histories. All plotted measurements come from the API. */
window.CLIMATE_DAILY_CHARTS = {
 render(target,data,helpers) {
  const {E,fmt,chart,table,csv,modal}=helpers;
  const station=data.station.station_name||data.station.station_id;
  let month=0,selected=0,visible=data.days,normalOverlay=true;
  target.innerHTML='<section class="ce-panel ce-daily-panel"><div class="ce-heading"><div><div class="ce-eyebrow">A year in daily weather</div><h3>'+E(station)+' · '+data.year+'</h3><p class="ce-muted ce-small">Daily temperature range, mean and rainfall · '+E(data.station.station_id)+'</p></div><div><button class="ce-year-csv">Daily data CSV</button> <button class="ce-year-svg">Save chart SVG</button> <button class="ce-year-png">Save chart PNG</button></div></div><div class="ce-controls"><label>Chart range<select class="ce-chart-month"><option value="0">Full year</option>'+Array.from({length:12},(_,i)=>'<option value="'+(i+1)+'">'+new Date(2000,i,1).toLocaleString("en-GB",{month:"long"})+'</option>').join("")+'</select></label><label class="ce-checkbox"><input type="checkbox" class="ce-chart-normal" checked> Show '+E(data.normal_period)+' mean normal</label><span class="ce-small ce-muted">Hover, tap, or use ← → on the chart to inspect a day.</span></div><div class="ce-year-main"></div><div class="ce-day-inspect" aria-live="polite"></div><p class="ce-small ce-muted">Eligible observations: temperature '+data.coverage.tmean_c+'/'+data.days.length+' days; rainfall '+data.coverage.precip_mm+'/'+data.days.length+' days. '+data.trace_days+' reported trace days. '+data.excluded_values+' variable values excluded by QC. Missing values remain gaps.</p><div class="ce-chart-feedback" role="status"></div></section><div class="ce-year-additional"></div><details class="ce-panel"><summary>Inspect daily measurements, samples and quality flags</summary><div class="ce-year-data"></div></details>';
  const main=target.querySelector(".ce-year-main"),details=target.querySelector(".ce-day-inspect");
  function path(points) {
   let active=false;
   return points.map(p=>{if(!p){active=false;return "";}const part=(active?"L":"M")+p.join(",");active=true;return part;}).join(" ");
  }
  function segments(rows,valid) {const result=[];let run=[];rows.forEach((r,i)=>{if(valid(r)){run.push(i);}else if(run.length){result.push(run);run=[];}});if(run.length)result.push(run);return result;}
  function draw(){
   visible=data.days.filter(d=>!month||Number(d.date.slice(5,7))===month);selected=Math.min(selected,visible.length-1);
   const w=1120,h=610,L=65,R=24,T=70,tempBottom=355,rainTop=420,rainBottom=550;
   const temps=visible.flatMap(d=>[d.values.tmin_c,d.values.tmax_c,d.values.tmean_c,normalOverlay?d.normal.tmean_c?.mean:null]).filter(v=>v!==null&&v!==undefined);
   const min=temps.length?Math.floor(Math.min(...temps)/10)*10:-10,max=Math.max(min+10,temps.length?Math.ceil(Math.max(...temps)/10)*10:40);
   const rains=visible.map(d=>d.values.precip_mm).filter(v=>v!==null),rainPeak=Math.max(5,...rains),rainStep=Math.max(1,Math.pow(10,Math.floor(Math.log10(rainPeak)))),rainMax=Math.ceil(rainPeak/rainStep)*rainStep;
   const x=i=>L+i*(w-L-R)/Math.max(1,visible.length-1),ty=v=>tempBottom-(v-min)/(max-min)*(tempBottom-T),ry=v=>rainBottom-v/rainMax*(rainBottom-rainTop);
   let svg='<svg class="ce-daily-svg" viewBox="0 0 '+w+' '+h+'" xmlns="http://www.w3.org/2000/svg" role="img" tabindex="0" aria-label="'+E(station+' daily temperature and rainfall in '+data.year)+'"><rect width="1120" height="610" fill="#f8fafc"/><text x="65" y="24" font-family="Arial" font-size="19" font-weight="bold" fill="#172c3c">'+E(station+' · Daily weather in '+data.year)+'</text><text x="65" y="46" font-family="Arial" font-size="12" fill="#607988">'+E(data.station.station_id+' · '+(month?new Date(2000,month-1,1).toLocaleString("en-GB",{month:"long"}):'January–December')+' · ANM historical observations')+'</text>';
   for(let v=min;v<=max;v+=10){const y=ty(v);svg+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+y+'" y2="'+y+'" stroke="#e2eaf0"/><text x="'+(L-10)+'" y="'+(y+4)+'" text-anchor="end" font-family="Arial" font-size="12" fill="#607988">'+fmt(v,0)+'</text>';}
   for(let v=0;v<=rainMax;v+=rainStep){const y=ry(v);svg+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+y+'" y2="'+y+'" stroke="#e2eaf0"/><text x="'+(L-10)+'" y="'+(y+4)+'" text-anchor="end" font-family="Arial" font-size="12" fill="#607988">'+fmt(v,0)+'</text>';}
   svg+='<text transform="translate(18,215) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="13" fill="#607988">Temperature (°C)</text><text transform="translate(18,490) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="13" fill="#607988">Rainfall (mm)</text>';
   for(const seg of segments(visible,d=>d.values.tmin_c!==null&&d.values.tmax_c!==null)){
    if(seg.length===1){const i=seg[0];svg+='<line x1="'+x(i)+'" x2="'+x(i)+'" y1="'+ty(visible[i].values.tmin_c)+'" y2="'+ty(visible[i].values.tmax_c)+'" stroke="#82afe1" stroke-width="3"/>';}
    const upper=seg.map(i=>[x(i),ty(visible[i].values.tmax_c)]),lower=[...seg].reverse().map(i=>[x(i),ty(visible[i].values.tmin_c)]);
    svg+='<path d="'+path(upper)+" L"+lower.map(p=>p.join(",")).join(" L")+' Z" fill="#a9c9ef" fill-opacity=".62" stroke="#82afe1" stroke-width=".6"/>';
   }
   svg+='<path d="'+path(visible.map((d,i)=>d.values.tmean_c===null?null:[x(i),ty(d.values.tmean_c)]))+'" fill="none" stroke="#285990" stroke-width="2"/>';
   for(const seg of segments(visible,d=>d.values.tmean_c!==null)){if(seg.length===1){const i=seg[0];svg+='<circle cx="'+x(i)+'" cy="'+ty(visible[i].values.tmean_c)+'" r="2.5" fill="#285990"/>';}}
   if(normalOverlay)svg+='<path d="'+path(visible.map((d,i)=>d.normal.tmean_c?.mean==null?null:[x(i),ty(d.normal.tmean_c.mean)]))+'" fill="none" stroke="#b98031" stroke-width="1.8" stroke-dasharray="6 4"/>';
   const barWidth=Math.max(1,(w-L-R)/visible.length*.78);
   visible.forEach((d,i)=>{
    const v=d.values.precip_mm;
    if(v!==null&&v>0)svg+='<rect x="'+(x(i)-barWidth/2)+'" y="'+ry(v)+'" width="'+barWidth+'" height="'+(rainBottom-ry(v))+'" fill="#218e9f"><title>'+E(d.date+': '+fmt(v)+' mm')+'</title></rect>';
    if(d.raw?.precip_trace&&v!==null)svg+='<circle cx="'+x(i)+'" cy="'+(rainBottom+5)+'" r="2" fill="#ab713a"><title>'+E(d.date+': trace precipitation')+'</title></circle>';
    if(v===null)svg+='<rect x="'+(x(i)-barWidth/2)+'" y="'+(rainBottom+10)+'" width="'+barWidth+'" height="3" fill="#a9b2b9"/>';
    if(d.raw&&(Object.keys(d.raw.excluded_variables).length||d.raw.verification_notes.length||d.raw.quality_flags.length))svg+='<circle cx="'+x(i)+'" cy="'+(T-8)+'" r="2.5" fill="#b77a24"><title>'+E(d.date+': quality details available')+'</title></circle>';
    if(month?i%5===0:d.date.endsWith("-01"))svg+='<text x="'+x(i)+'" y="579" text-anchor="middle" font-family="Arial" font-size="12" fill="#607988">'+E(month?d.date.slice(8):new Date(d.date+"T12:00:00").toLocaleString("en-GB",{month:"short"}))+'</text>';
   });
   if(!temps.length)svg+='<text x="550" y="220" text-anchor="middle" font-family="Arial" fill="#607988">No eligible temperature observations</text>';
   if(!rains.length)svg+='<text x="550" y="480" text-anchor="middle" font-family="Arial" fill="#607988">No eligible rainfall observations</text>';
   svg+='<text x="65" y="603" font-family="Arial" font-size="11" fill="#607988">Source: ANM · Blue band: Tmin–Tmax · Blue line: mean · Dashed gold: normal · Brown dots: trace · Grey marks: missing rain · Gold dots: QC details</text><line class="ce-day-guide" x1="'+x(selected)+'" x2="'+x(selected)+'" y1="'+T+'" y2="'+rainBottom+'" stroke="#476b7a" stroke-dasharray="3 3" opacity=".5"/></svg>';
   main.innerHTML=svg;
   const el=main.querySelector("svg");
   function inspect(i){selected=Math.max(0,Math.min(visible.length-1,i));const d=visible[selected],r=d.raw;const guide=el.querySelector(".ce-day-guide");guide.setAttribute("x1",x(selected));guide.setAttribute("x2",x(selected));
    details.innerHTML='<strong>'+E(d.date)+'</strong><span>Tmin '+E(fmt(d.values.tmin_c))+' °C</span><span>Mean '+E(fmt(d.values.tmean_c))+' °C</span><span>Tmax '+E(fmt(d.values.tmax_c))+' °C</span><span>Rain '+(r?.precip_trace&&d.values.precip_mm!==null?'trace':E(fmt(d.values.precip_mm))+' mm')+'</span><span>Normal mean '+E(fmt(d.normal.tmean_c?.mean))+' °C · n='+E(d.normal.tmean_c?.sample_count??0)+'</span><button class="ce-inspect-source">Inspect source / QC</button>';
    details.querySelector("button").onclick=()=>modal(d.date+" · observation details",r?'<p>Source: '+E(r.source_member+":"+r.source_line)+'</p>'+table(["Variable","Raw value","Chart value","QC exclusion"],Object.keys(d.values).map(v=>[E(v),E(fmt(r[v])),E(fmt(d.values[v])),E(r.excluded_variables[v]||"None")]))+'<p>Original flags: '+E(JSON.stringify(r.quality_flags))+'</p><p>'+E(r.verification_notes.map(n=>n.review_reason).join(" "))+'</p>':'<p>No source observation exists for this date.</p>');
   }
   el.onpointermove=e=>{const pt=el.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const p=pt.matrixTransform(el.getScreenCTM().inverse());inspect(Math.round((p.x-L)/(w-L-R)*(visible.length-1)));};
   el.onkeydown=e=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();inspect(selected+(e.key==="ArrowLeft"?-1:1));}};
   inspect(selected);additional();
   target.querySelector(".ce-year-data").innerHTML=table(["Date","Tmin °C","Mean °C","Tmax °C","Rain mm","Rain state","Normal n years","Quality"],visible.map(d=>[E(d.date),...["tmin_c","tmean_c","tmax_c","precip_mm"].map(v=>E(fmt(d.values[v]))),d.raw?.precip_trace?"Trace":d.values.precip_mm===0?"Dry":d.values.precip_mm===null?"Missing":"Measurable",E(d.normal.tmean_c?.sample_count??0),E(d.raw?JSON.stringify({flags:d.raw.quality_flags,excluded:d.raw.excluded_variables,review:d.raw.verification_notes}):"No source row")]));
  }
  function additional(){
   let observed=0,baseline=0,baselineComplete=true;
   const totals=data.days.map(d=>{if(d.values.precip_mm!==null)observed+=d.values.precip_mm;if(d.normal.precip_mm?.mean==null)baselineComplete=false;else baseline+=d.normal.precip_mm.mean;return {date:d.date,actual:d.values.precip_mm===null?null:observed,normal:baselineComplete?baseline:null};}).filter(d=>!month||Number(d.date.slice(5,7))===month);
   const range=visible[0].date+" to "+visible.at(-1).date;
   const labels=visible.map(d=>d.date.slice(5)),extra=target.querySelector(".ce-year-additional");
   extra.innerHTML=chart("Daily mean temperature anomaly · "+data.normal_period,labels,[{name:"Daily anomaly",color:"#b56b47",values:visible.map(d=>d.tmean_anomaly)}],"°C",range)+
   chart("Cumulative rainfall · from 1 January",totals.map(d=>d.date.slice(5)),[{name:"Observed running subtotal",color:"#218e9f",values:totals.map(d=>d.actual)},{name:"Sum of daily mean normals",color:"#b98031",values:totals.map(d=>d.normal)}],"mm",range)+
   '<p class="ce-muted ce-small">Observed accumulation omits missing/QC-excluded rainfall; it is a subtotal when coverage is incomplete. A missing daily normal stops the reference accumulation. The reference sums daily means, not independently computed monthly normals.</p>';
  }
  function save(blob,name){const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function imageSVG(){
   const s=main.querySelector("svg").cloneNode(true),ns="http://www.w3.org/2000/svg";
   s.querySelector(".ce-day-guide")?.remove();
   // Reserve a separate footer so branding never overlaps the chart or source credit.
   const {width,height}=s.viewBox.baseVal,exportHeight=height+40;
   s.setAttribute("viewBox","0 0 "+width+" "+exportHeight);
   s.setAttribute("width",width);s.setAttribute("height",exportHeight);
   s.querySelector("rect").setAttribute("height",exportHeight);
   const copyright=document.createElementNS(ns,"text");
   for(const [key,value] of Object.entries({x:65,y:height+25,"font-family":"Arial","font-size":14,fill:"#172c3c"}))copyright.setAttribute(key,value);
   copyright.textContent="© WxProbs";s.append(copyright);
   return new XMLSerializer().serializeToString(s);
  }
  target.querySelector(".ce-chart-month").onchange=e=>{month=Number(e.target.value);selected=0;draw();};
  target.querySelector(".ce-chart-normal").onchange=e=>{normalOverlay=e.target.checked;draw();};
  target.querySelector(".ce-year-svg").onclick=()=>save(new Blob([imageSVG()],{type:"image/svg+xml"}),data.station.station_id+"-"+data.year+".svg");
  target.querySelector(".ce-year-png").onclick=async()=>{const feedback=target.querySelector(".ce-chart-feedback");try{const img=new Image(),url=URL.createObjectURL(new Blob([imageSVG()],{type:"image/svg+xml"}));try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url;});const c=document.createElement("canvas");c.width=img.naturalWidth*2;c.height=img.naturalHeight*2;c.getContext("2d").drawImage(img,0,0,c.width,c.height);const blob=await new Promise(resolve=>c.toBlob(resolve,"image/png"));if(!blob)throw Error("PNG export failed");save(blob,data.station.station_id+"-"+data.year+".png");feedback.textContent="PNG chart downloaded.";}finally{URL.revokeObjectURL(url);}}catch(e){feedback.textContent="Unable to export PNG. SVG export is available.";console.error(e);}};
  target.querySelector(".ce-year-csv").onclick=()=>csv(data.station.station_id+"-"+data.year+"-daily.csv",["date","source_present","tmin_c","tmean_c","tmax_c","precip_mm","trace","normal_tmean_c","normal_sample_years","tmean_anomaly_c","raw_values","excluded_variables","original_flags","verification_notes"],visible.map(d=>[d.date,d.source_present,d.values.tmin_c,d.values.tmean_c,d.values.tmax_c,d.values.precip_mm,d.raw?.precip_trace,d.normal.tmean_c?.mean,d.normal.tmean_c?.sample_count,d.tmean_anomaly,d.raw,d.raw?.excluded_variables,d.raw?.quality_flags,d.raw?.verification_notes]));
  draw();
 }
};
