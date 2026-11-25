from chem import Chem
rows=["| M | p=0.01 | p=0.02 | p=0.03 | p=0.05 | p=0.08 |","|---|---|---|---|---|---|"]
for M in (150,300,600):
    r=[]
    for p in (0.01,0.02,0.03,0.05,0.08):
        n=0
        for sd in range(1,11):
            c=Chem(seed=sd,p=p,M=M).run(500*M)
            n+= len(c.organization(cleave=False))>=2
        r.append(f"{n}/10")
    rows.append(f"| {M} | "+" | ".join(r)+" |"); print(rows[-1],flush=True)
open('REDTEAM_size.md','w').write("# Доля прогонов с формой (ligation-only) при разном размере M, T=500·M, 10 seed\n\n"+"\n".join(rows)+"\n")
