import React, { useEffect, useState } from 'react';

type Total = { visits:number; since:string|null };
// One request per page load, even if React remounts the footer.
let request:Promise<Total|null>|undefined;
function loadTotal(){
  if(!request) request=(async()=>{
    if(location.origin!=='https://romanian-climate-explorer.vercel.app') return null;
    try {
      const response=await fetch('/api/visits',{
        method:'POST', headers:{'X-RCE-Visit':'1'}, credentials:'same-origin',
        signal:AbortSignal.timeout(8000),
      });
      if(!response.ok) return null;
      const result=await response.json() as Total;
      return Number.isSafeInteger(result.visits)&&result.visits>=0?result:null;
    } catch { return null; }
  })();
  return request;
}

export function VisitCounter(){
  const [total,setTotal]=useState<Total|null>(null);
  useEffect(()=>{let active=true;void loadTotal().then(value=>{if(active)setTotal(value);});return()=>{active=false;};},[]);
  if(!total) return null;
  return <span className="visit-counter" title={`Visits counted since ${total.since??'launch'}. Repeat visits within 30 minutes count once when cookies are enabled. This is not a unique-person count.`}>
    {total.visits.toLocaleString('en-GB')} {total.visits===1?'visit':'visits'}
    {total.since&&<small> since {new Date(total.since+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}</small>}
  </span>;
}
