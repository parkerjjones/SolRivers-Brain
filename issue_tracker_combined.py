#!/usr/bin/env python3
"""Combines original Issue Tracker CSV with new 6/9/2026 alert rows and uploads to Google Drive."""
import csv, io

ORIGINAL_CSV = """\
Timestamp,Email Address,Project Name,Equipment,SubPart,Description of Issue (In 2 words or less),Quantity,Equipment ID,Start Date,Comment,Category,End Date,Action Taken,Score,"Does the issue cause Production Loss? (1 - yes, 0 - no)",SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,SubPart,Start Time (If available),End time (If available),Screenshots (E,Column 14
8/5/2025 17:34:24,abhinav@solrivercapital.com,Graham,Inverter,,Offline,1,32,7/5/2025,,Repair,,,,,,,,,,,,,,,,,,,
3/30/2026 17:42:44,abhinav@solrivercapital.com,Elk,Site,,Utility Planned Outage,1,,3/16/2026,"The utility took 2/3 of the site offline as part of a planned outage due to repairs on utility side.",Outage,,,,1,,,,,,,,,,,,,,,
4/15/2026 13:14:22,abhinav@solrivercapital.com,Longleaf,Inverter,,Damaged,1,A7,4/1/2026,"Inverter A7 went offline when the VM crew accidentally cut the DC string/ground wire, causing the AC Breaker and the inv itself to fault, and need replacement. Cost billed to sub contractor.",Equip Replace,4/14/2026,,,1,,,,,,,,,,,,,,,
4/15/2026 13:21:27,abhinav@solrivercapital.com,Whitehall,Customer POI,,Repair,1,Phase B,3/25/2026,Phase B fuse at the POI is hotter than Phase A and Phase C - We are raising workmanship warranty,Repair,,,,0,,,,,,,,,,,,,,,
4/15/2026 13:26:19,abhinav@solrivercapital.com,Shorthorn,Xfmr,AC Breaker,Tripped Offline,1,3,3/27/2026,"Pad 3 went offline on 3/27/2026, as the Main AC Breaker had tripped. NRCO was onsite on 3/28 and brought it online.",Repair,3/28/2026,,,1,,,,,,,,,,,,,,,
4/15/2026 13:41:39,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,2,3/6/2026,"Inverter 2 experienced a thermal event on 3/6. Solectria to send a spare, and take damaged unit for RCA",Equip Replace,,,,1,,,,,,,,,,,,,,,
4/15/2026 13:43:21,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,9,4/27/2026,"Inverter 9 experienced a thermal event on 3/27. Solectria to send a spare, and take damaged unit for RCA",Equip Replace,,,,1,,,,,,,,,,,,,,,
4/15/2026 13:48:47,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,35,4/6/2026,"Inverter 35 experienced a thermal event on 4/6. Solectria to send a spare, and take damaged unit for RCA",Equip Replace,,,,1,,,,,,,,,,,,,,,
4/24/2026 11:07:13,abhinav@solrivercapital.com,Elk,Site,,Utility Trip,1,,4/23/2026,"Elk experienced a site trip on 4/23/2026 at 7:40 am. NCC reclosed it remotely at 11:21 am, same day.",Outage,4/23/2026,,,1,,,,,,,,,,,,,,,
5/6/2026 11:21:48,abhinav@solrivercapital.com,Whitetail,Site,,Utility Trip,1,,4/18/2026,Utility trip from 6pm on 4/18 to 7:15 am on 4/19,Outage,4/19/2026,,,1,,,,,,,,,,,,,,,
5/6/2026 11:22:54,abhinav@solrivercapital.com,Warbler,Site,,Utility Trip,1,,4/25/2026,Utility trip from 4pm on 4/25 to 7:31 am on 4/26,Outage,4/26/2026,,,1,,,,,,,,,,,,,,,
5/6/2026 11:25:15,abhinav@solrivercapital.com,Longleaf,Utility Side,,Derate,0.5,,5/5/2026,"The utility has conducted a planned derate and site has been derated by 2.5 mw from 5/5 6pm to 5/6 9 pm (expected)",Outage,,,,1,,,,,,,,,,,,,,,
5/18/2026 9:51:58,abhinav@solrivercapital.com,Gray Fox,Inverter,,Offline,1,2.6,5/17/2026,"Inv 2.6 went offline again on 5/17/2026. Cause currently unknown",Repair,,,,1,,,,,,,,,,,,,,,
5/18/2026 10:01:09,abhinav@solrivercapital.com,RRH,Inverter,,Tripped Offline,1,2-11,5/15/2026,"Inv tripped offline on 3/15 and had an ARC Protection alert. It was resolved on 3/18.",Repair,5/18/2026,,,1,,,,,,,,,,,,,,,
5/19/2026 14:56:12,abhinav@solrivercapital.com,Eagle,Site,,Tripped Offline,1,,5/19/2026,"Utility tripped site offline at 10, but site did not come back online even after utility brought it online. TMI sent sub (Kinner electric) onsite to check the issue and they found site offline, and had to use standby generator to bring it online at 4:30 pm.",Outage,5/19/2026,,,1,,,,,,,,,,,,,,,
5/28/2026 13:08:24,abhinav@solrivercapital.com,Williams,Inverter,,Tripped Offline,1,A20,5/26/2026,"Inv A20 tripped offline on 5/26, and NRCO sent a tech on site on 5/28. The tech was able to bring it back online. Awaiting update on cause and repair.",Repair,5/28/2026,,,1,,,,,,,,,,,,,,,
5/28/2026 13:09:54,abhinav@solrivercapital.com,RIT,Site,,Offline,1,,5/27/2026,"RIT tripped offline on 5/27. MB reached out on 5/28, and is scheduled to be onsite on 5/29, for a quote of $1k.",Outage,,,,1,,,,,,,,,,,,,,,
5/28/2026 13:25:38,abhinav@solrivercapital.com,Elk,Inverter,,Offline,7,"1.01 - 1.07",5/27/2026,"Invs 1.01 - 1.07 appear to have gone offline / stopped communicating on 5/27. May have come back online on 5/29. Awaiting update and confirmation, as well as cause.",Outage,,,,0,,,,,,,,,,,,,,,
5/28/2026 13:39:27,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,8,4/14/2026,"Inv 8 experienced a thermal event on 4/14. All 3 IGBTS had damage but A Phase had damage to the point that the snubber caps blew off and the bus connection point between the IGBT and the filter caps.",Replacement,,,,1,,,,,,,,,,,,,,,
5/28/2026 13:43:36,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,23,4/10/2026,"Inverter 23 failed on 4/10/26 at 10:09 AM. The failure was to all 3 IGBTs with a concentration of damage on the A phase. The snubber caps were blown off on the A phase.",Replacement,,,,1,,,,,,,,,,,,,,,
5/28/2026 13:47:45,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,17,5/11/2026,Inv 17 experienced a thermal event on May 11.,Replacement,,,,1,,,,,,,,,,,,,,,
5/28/2026 13:48:36,abhinav@solrivercapital.com,Graham,Inverter,,Thermal Event,1,13,5/28/2026,Inverter 13 experienced a thermal event on 5/28/2026.,Replacement,,,,1,,,,,,,,,,,,,,,
6/1/2026 14:33:04,abhinav@solrivercapital.com,Whitetail,Inverter,,Thermal Event,1,1,6/1/2026,Inverter thermal event,Replacement,,,,1,,CT,,,,,,,,,,,,,
6/5/2026 10:21:42,abhinav@solrivercapital.com,Shorthorn,Site,,Offline,1,,6/5/2026,Site went offline on 6/5/2026 at 10:15 am. Duke recloser status is closed. Pinged NRCO.,Outage,,,,1,,,,,,,,,,,,10:15:00 AM,,,
6/5/2026 10:23:03,abhinav@solrivercapital.com,Williams,Inverter,,Tripped Offline,1,A20,6/4/2026,Inverter A20 Tripped offline on 6/4. Pinged NRCO.,Outage,,,,1,,,,,,,,,,,,4:45:00 PM,,,"""

# Read original rows
original_rows = list(csv.reader(io.StringIO(ORIGINAL_CSV)))
header = original_rows[0]
data_rows = original_rows[1:]

# Read new rows
with open('tracker_new_rows_609.csv', encoding='utf-8') as f:
    new_rows = list(csv.reader(f))

all_rows = [header] + data_rows + new_rows

# Write combined CSV
out = io.StringIO()
writer = csv.writer(out, lineterminator='\n')
writer.writerows(all_rows)
combined_csv = out.getvalue()

print(f"Original rows: {len(data_rows)}")
print(f"New rows:      {len(new_rows)}")
print(f"Total:         {len(data_rows) + len(new_rows)}")

with open('issue_tracker_combined.csv', 'w', encoding='utf-8', newline='') as f:
    f.write(combined_csv)
print("Saved -> issue_tracker_combined.csv")

# Make available for upload
import sys
sys.stdout.flush()
print("\nCSV_CONTENT_START")
print(combined_csv[:500])
print("CSV_CONTENT_END")
