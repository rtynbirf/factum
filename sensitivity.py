import emergent as E, statistics as st
BASE=['S','K','I',('K','I'),('S','K'),('S','I'),('K','K'),(('S','K'),'K')]
EXTRA=[('I','I'),(('S','I'),'I'),(('K','S'),'K'),(('S','S'),'K')]
sets={"4 зонда":BASE[:4],"8 зондов":BASE,"12 зондов":BASE+EXTRA}
rows=["| зонды | cap | N1 | N2 | N3 | доля N3 среди новых |","|---|---|---|---|---|---|"]
for pn,pr in sets.items():
    E.set_probes(pr)
    for cap in (35,70,140):
        v=[0,0,0,0]
        for sd in range(1,9):
            w=E.World(seed=sd,inflow=0.5,cap=cap).run(2000)
            for i,x in enumerate(E.novelty_vector(w)): v[i]+=x
        v=[x/8 for x in v]; tot=v[1]+v[2]+v[3]
        rows.append(f"| {pn} | {cap} | {v[1]:.0f} | {v[2]:.0f} | {v[3]:.0f} | {v[3]/tot:.2f} |")
        print(rows[-1],flush=True)
E.set_probes(BASE)
open('SENSITIVITY.md','w').write("# Чувствительность уровней новизны ν к зонду и cap (8 seed, среднее на прогон, T=2000)\n\n"+"\n".join(rows)+"\n")
