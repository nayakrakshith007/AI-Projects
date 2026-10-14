"""Build discovery/sources_raw.csv from the two directory workbooks (remote sheet from file (1), GCC sheet from file (2))."""
import csv, openpyxl
import sys
R = sys.argv[1] if len(sys.argv) > 1 else 'Remote_AI_ML_Jobs_Directory (1).xlsx'      # the two directory workbooks are passed in, not shipped
G = sys.argv[2] if len(sys.argv) > 2 else 'Remote_AI_ML_Jobs_Directory (2).xlsx'
rows = []
ws = openpyxl.load_workbook(R)['All Remote AI Jobs']
for r in ws.iter_rows(min_row=3, values_only=True):
    if r[0] and str(r[0]).strip().isdigit():
        rows.append(dict(id=f"R{int(r[0]):02d}", sheet='remote', name=r[1], url=r[2], category=r[3], notes=r[4]))
wb = openpyxl.load_workbook(G)
g = wb[wb.sheetnames[-1]]
for r in g.iter_rows(min_row=3, values_only=True):
    if r[0] and str(r[0]).strip().isdigit():
        rows.append(dict(id=f"G{int(r[0]):02d}", sheet='gcc', name=r[1], url=r[3], category=r[2], notes=r[4]))
with open('discovery/sources_raw.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), sum(r['sheet']=='remote' for r in rows), sum(r['sheet']=='gcc' for r in rows))
