import emergent as E
from collections import Counter
rows=[]; out=[]
def jac(a,b):
    a,b=set(a),set(b); return len(a&b)/max(1,len(a|b))
out.append("| режим | seed | типов | N1 | N2 | N3 | форма F(t=1000) | F(2000) | F(3000) |")
out.append("|---|---|---|---|---|---|---|---|---|")
for inflow in (0.0, 0.5):
    for sd in range(1,6):
        w=E.World(seed=sd,inflow=inflow); f=[]
        for _ in range(3): w.run(1000); f.append(len(w.organization()))
        n=E.novelty_vector(w)
        out.append(f"| inflow={inflow} | {sd} | {len(set(w.W))} | {n[1]} | {n[2]} | {n[3]} | {f[0]} | {f[1]} | {f[2]} |")
w0=E.World(seed=0).W
A=E.World(seed=1,w0=w0,inflow=0.5).run(3000); B=E.World(seed=2,w0=w0,inflow=0.5).run(3000)
C=E.World(seed=1,w0=w0,inflow=0.5).run(3000)
out.append("")
out.append(f"Путезависимость: одно W0, разные истории -> Жаккар типов = {jac(A.W,B.W):.2f}; та же история -> {jac(A.W,C.W):.2f}")
out.append(f"Символы в истории: {sorted(A.sigma_used())} (ΔΣ = 0)")
open('RESULTS.md','w').write("# RESULTS (сгенерировано experiment.py)\n\nN1 = новый терм, поведение уже было; N2 = композиция известных операций (∈Cl₁ истории); N3 = поведение вне Cl₁ истории (относительно зонда из 8 термов и ≤70 представителей). N0 в таблице нет: это не-новые термы.\n\n"+"\n".join(out)+"\n")
print("\n".join(out))
