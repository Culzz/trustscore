import pandas as pd
pd.set_option("display.width", 200)
df = pd.read_csv(r"C:\Users\hp\Documents\Default Project\trustscore\data\raw\credit_risk_dataset.csv")
print("shape:", df.shape)
print("\ndtypes:\n", df.dtypes)
print("\nmissing:\n", df.isna().sum())
print("\ntarget:\n", df["loan_status"].value_counts(dropna=False))
print("\nduplicated rows:", df.duplicated().sum())
print("\nnumeric describe:\n", df.describe().T)
for c in ["person_home_ownership","loan_intent","loan_grade","cb_person_default_on_file"]:
    print(f"\n{c}:", dict(df[c].value_counts(dropna=False)))
print("\nage > 100:", (df["person_age"]>100).sum())
print("emp_length > 60:", (df["person_emp_length"]>60).sum())
