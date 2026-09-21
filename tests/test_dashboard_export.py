"""Check freshness and QC handling at the new production build boundary."""
from contextlib import nullcontext
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.export_dashboard import export

class DashboardExportTests(unittest.TestCase):
    def test_snapshot_date_drives_last_full_year_and_ineligible_values_stay_missing(self):
        station={'station_id':'test-station','station_name':'Test station','latitude':44.0,'longitude':26.0,
                 'first_observation':'1961-01-01','last_observation':'2027-02-01','completeness_percent':90}
        explorer=Mock()
        explorer.catalogue.return_value=[station]
        explorer.products.policy={'normal':'1991-2020'}
        explorer.products.db.execute.return_value=[{'year':2026,'data_json':json.dumps({'variables':{
            'tmean_c':{'eligible':True,'mean':11.123456,'anomaly':1.1},
            'precip_mm':{'eligible':False,'total':400,'anomaly':-50}}})}]
        with tempfile.TemporaryDirectory() as directory, patch('scripts.export_dashboard.Explorer',return_value=nullcontext(explorer)), patch('scripts.export_dashboard.date') as clock:
            clock.today.return_value=date(2027,2,2)
            result=export(output=Path(directory)/'dashboard.json')
            self.assertEqual(result['snapshotDate'],'2027-02-01')
            self.assertEqual(result['lastYear'],2026)
            self.assertEqual(result['stations'][0]['history'][0],{'year':2026,'temp':11.1235,'tempAnomaly':1.1,'rain':None,'rainAnomaly':None})
            self.assertEqual(explorer.products.db.execute.call_args.args[1],('test-station',1961,2026))

    def test_archive_ending_on_december_31_retains_that_completed_year(self):
        explorer=Mock()
        explorer.catalogue.return_value=[{'station_id':'test','station_name':'Test','latitude':44,'longitude':26,
            'first_observation':'1961-01-01','last_observation':'2025-12-31','completeness_percent':100}]
        explorer.products.policy={'normal':'1991-2020'}
        explorer.products.db.execute.return_value=[]
        with tempfile.TemporaryDirectory() as directory, patch('scripts.export_dashboard.Explorer',return_value=nullcontext(explorer)), patch('scripts.export_dashboard.date') as clock:
            clock.today.return_value=date(2026,1,1)
            self.assertEqual(export(output=Path(directory)/'dashboard.json')['lastYear'],2025)
