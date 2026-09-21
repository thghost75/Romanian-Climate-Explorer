import React, {useEffect,useRef} from 'react';
import './daily-charts.js';
import {mountArchive,type ArchiveChange,type ArchiveState} from './archive-engine.js';

export function ArchivePane({state,onChange}:{state:ArchiveState;onChange:(change:ArchiveChange)=>void}){
 const ref=useRef<HTMLDivElement>(null);
 const engine=useRef<ReturnType<typeof mountArchive>|null>(null);
 const callback=useRef(onChange);callback.current=onChange;
 useEffect(()=>{engine.current=mountArchive(ref.current!,change=>callback.current(change));return()=>{engine.current?.destroy();engine.current=null;};},[]);
 useEffect(()=>{void engine.current?.update(state);},[state.station,state.tab,state.year,state.month,state.day,state.normal]);
 return <div ref={ref} className="climate-app archive-pane" aria-label="Historical climate archive"/>;
}
