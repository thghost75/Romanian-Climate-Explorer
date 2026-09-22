"""Build annual dashboard data from the verified deployment snapshot, read-only."""
import json
import sys
from datetime import date
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from anm_climate.explorer_api import Explorer

def export(data_root=None, output=None):
    output=Path(output or PROJECT/'frontend/src/data.json')
    with Explorer(data_root or PROJECT/'data/anm') as explorer:
        catalogue=explorer.catalogue()
        latest=max(s['last_observation'] for s in catalogue)
        last_year=min(date.today().year-1,int(latest[:4])-(latest[5:]!='12-31'))
        first_year=min(int(s['first_observation'][:4]) for s in catalogue)
        stations=[]
        def rounded(value):return round(value,4) if value is not None else None
        for station in catalogue:
            history=[]
            for row in explorer.products.db.execute(
                'SELECT year,data_json FROM annual_summary WHERE station_id=? AND year BETWEEN ? AND ? ORDER BY year',
                (station['station_id'],first_year,last_year)):
                variables=json.loads(row['data_json'])['variables']
                temp,rain=variables['tmean_c'],variables['precip_mm']
                history.append({'year':row['year'],
                    'temp':rounded(temp.get('mean')) if temp.get('eligible') else None,
                    'tempAnomaly':rounded(temp.get('anomaly')) if temp.get('eligible') else None,
                    'rain':rounded(rain.get('total')) if rain.get('eligible') else None,
                    'rainAnomaly':rounded(rain.get('anomaly')) if rain.get('eligible') else None})
            stations.append({'id':station['station_id'],'name':station['station_name'],
                'lat':station['latitude'],'lon':station['longitude'],
                'first':station['first_observation'],'last':station['last_observation'],
                'coverage':rounded(station['completeness_percent']),'history':history})
        result={'stations':stations,'baseline':explorer.products.policy['normal'],
            'snapshotDate':latest,'firstYear':first_year,'lastYear':last_year}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
        print(f'Dashboard regenerated: {len(stations)} stations; snapshot {latest}; annual data through {last_year}.',flush=True)
        return result

if __name__=='__main__':export()
