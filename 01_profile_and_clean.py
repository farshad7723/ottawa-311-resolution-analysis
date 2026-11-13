"""
Ottawa 311 Service Requests - profiling and cleaning (progress so far)

Data: City of Ottawa Open Data, "Current Year Service Requests"
Downloaded: 2026-11-09 (the file is refreshed daily, so counts change)
"""
import pandas as pd

# 1) Load the raw file (never edit the raw file; keep it in data/raw/)
df = pd.read_csv('311opendata_currentyear.csv')

# 2) Clean column names: headers are bilingual, e.g. "Status | Etat".
#    split on "|", keep the English part, strip the leftover space.
df.columns = df.columns.str.split('|').str[0].str.strip()
print(df.columns.tolist())
print(df.shape)  # observed: (323366, 11)

# 3) Missing values are hidden: isna() reports 0, but active requests
#    store "\N" as text in Closed Date. Inspect before trusting isna().
print(df['Status'].value_counts(dropna=False))
# observed: Resolved 297085, Active 22123, Cancelled 4158

# 4) Convert text to real dates. errors='coerce' turns "\N" into NaT.
df['Opened Date'] = pd.to_datetime(df['Opened Date'], errors='coerce')
df['Closed Date'] = pd.to_datetime(df['Closed Date'], errors='coerce')

# Validation: NaT in Closed Date must equal the Active count,
# otherwise coerce silently swallowed something else.
print('Opened NaT:', df['Opened Date'].isna().sum())            # observed: 0
print('Closed NaT:', df['Closed Date'].isna().sum())            # observed: 22123
print('Active    :', (df['Status'] == 'Active').sum())          # observed: 22123

# 5) Keep only Resolved requests for resolution time.
#    Active = still open (no close date). Cancelled = close date is
#    probably the cancellation date (assumption), so it is excluded too.
resolved = df[df['Status'] == 'Resolved'].copy()

# 6) Metric: days from opened to closed
resolved['resolution_days'] = (
    resolved['Closed Date'] - resolved['Opened Date']
).dt.days
print(resolved['resolution_days'].describe())
# observed: median 2, mean 19.6, max 310, negatives 0
print('Negative:', (resolved['resolution_days'] < 0).sum())

# 7) Find days with unusual closing behaviour: many closures AND a very
#    high median age of the closed requests.
by_day = resolved.groupby('Closed Date')['resolution_days'].agg(['count', 'median'])
print(by_day.sort_values('median', ascending=False).head(10))
# observed top 3 by median age: 2026-10-06 (141), 2026-05-21 (99), 2026-05-22 (38)

# 8) Flag those three days as suspected bulk closures (a judgment call:
#    document it and run a sensitivity check with and without them).
bulk_dates = pd.to_datetime(['2026-05-21', '2026-05-22', '2026-10-06'])
resolved['bulk_closed'] = resolved['Closed Date'].isin(bulk_dates)

# 9) Analysis dataset without the flagged days
clean = resolved[~resolved['bulk_closed']].copy()
print(len(resolved), resolved['bulk_closed'].sum(), len(clean))
# observed: len(clean) = 255284 (the per-type counts below sum to this number);
# flagged rows = 297085 - 255284 = 41801


# ---------------------------------------------------------------
# ANALYSIS SO FAR (2026-11-11)
# ---------------------------------------------------------------

# A) Resolution time by request type: count, median, 95th percentile
by_type = clean.groupby('Type')['resolution_days'].agg(
    count='count',
    median='median',
    p95=lambda s: s.quantile(0.95)
)
print(by_type.sort_values('median', ascending=False))
print('Total:', by_type['count'].sum())   # observed: 255284

# B) Wards within one type (Roads and Transportation)
roads = clean[clean['Type'] == 'Roads and Transportation']
by_ward = roads.groupby('Ward')['resolution_days'].agg(
    count='count',
    median='median',
    p90=lambda s: s.quantile(0.9)
)
print(by_ward.sort_values('median', ascending=False))
# observed: Ward "\N" (unknown) shows up as a row; wards 1-24 otherwise

# C) Unknown wards ("\N"): how many, and where?
print('Unknown ward rows:', (clean['Ward'] == '\\N').sum())   # observed: 26040
print(clean[clean['Ward'] == '\\N']['Type'].value_counts())

known = clean[clean['Ward'] != '\\N']

# D) Spread of the median across wards, for the large types
big_types = ['Garbage and Recycling', 'Bylaw Services',
             'Parking Control Enforcement', 'Water and the Environment',
             'Roads and Transportation']
for t in big_types:
    med = known[known['Type'] == t].groupby('Ward')['resolution_days'].median()
    print(t, '| min median:', med.min(), '| max median:', med.max())

# E) Do requests without a ward differ from requests with a ward?
clean['ward_known'] = clean['Ward'] != '\\N'
check = clean[clean['Type'].isin(['Water and the Environment',
                                  'Garbage and Recycling'])]
print(check.groupby(['Type', 'ward_known'])['resolution_days']
           .agg(['count', 'median']))
# observed: Water unknown-ward median 9 vs known-ward median 3; Garbage 2 vs 2

water_unknown = clean[(clean['Type'] == 'Water and the Environment')
                      & (~clean['ward_known'])]
print(water_unknown['Description'].value_counts().head(8))
# observed: 13,345 of 14,691 have Description "\N"; 1,313 tree permit requests

# F) Sensitivity analysis: medians with and without the three flagged days
with_flagged = resolved.groupby('Type')['resolution_days'].median()
without_flagged = clean.groupby('Type')['resolution_days'].median()
compare = pd.DataFrame({'with_flagged': with_flagged,
                        'without_flagged': without_flagged})
print(compare.sort_values('without_flagged', ascending=False))
# observed: Roads 33 vs 3, Licenses 35 vs 15, Citizen Services 23 vs 6,
#           City Facilities 16 vs 4, Water 10 vs 5; Bylaw/Garbage/Parking unchanged

# G) Export for the dashboard
by_type.reset_index().to_csv('summary_by_type.csv', index=False)
clean.to_csv('clean_resolved.csv', index=False)
compare.reset_index().to_csv('sensitivity_by_type.csv', index=False)
print('Saved:', len(clean), 'rows')   # observed: 255284

# ---------------------------------------------------------------
# PARKED (optional, for later)
# ---------------------------------------------------------------
# is_hidden = water_unknown['Description'] == '\\N'
# print(water_unknown.groupby(is_hidden)['resolution_days'].agg(['count', 'median']))
# tree = water_unknown['Description'].str.startswith('Forestry - Distinctive Tree Permit')
# print(water_unknown[tree]['resolution_days'].agg(['count', 'median']))
# print((clean == '\\N').sum())
