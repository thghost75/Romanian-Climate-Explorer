export type ArchiveTab = 'overview' | 'on-day' | 'on-month' | 'on-year' | 'records' | 'temperature' | 'rainfall' | 'extremes' | 'history';
export type ArchiveChange = {station?:string; tab?:ArchiveTab; year?:number};
export type ArchiveState = {station:string; tab:ArchiveTab; year:number; month:number; day:number; normal:string; nationalPeriodYear:number|null};
export function mountArchive(host:HTMLElement,onChange:(change:ArchiveChange)=>void):{update(state:ArchiveState):Promise<void>;destroy():void};
