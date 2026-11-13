import numpy as np

# Nuzzo inverse: n_fail -> u
NZ = [(0.95,3.28),(0.90,4.94),(0.85,7.15),(0.80,9.75),(0.75,12.37),
      (0.70,14.80),(0.65,17.11),(0.60,19.53),(0.55,22.43),(0.50,25.99)]
ns = [n for _,n in NZ][::-1]; us = [u for u,_ in NZ][::-1]
def u_of(n):
    if n < 3.28: return 1.00 - 0.05*(n-1)/2.28   # v0.2 near-maximal extension
    if n > 25.99: return 0.50
    return float(np.interp(n, ns, us))

phiS = {0:1.00,1:0.95,2:0.85,3:0.72,4:0.58,5:0.45}
phiF = {0:1.35,1:1.15,2:1.00,3:0.90,4:0.82}
phiN = {0:1.30,1:1.15,2:1.00}
def pS(q): return phiS.get(q,0.30)
def pF(q): return phiF.get(q,0.75)
def pN(q): return phiN.get(q,0.90)
def psiR(r): return min(max(0.80+0.02*r,0.86),1.20)
d0,n0,g0 = 0.12,0.10,0.07

# exercise: (kappa, b, {muscle: cF})
EX = {
 'squat':    (0.95,0.90,{'quads':1.0,'glutes':0.5,'hams':0.5,'erectors':0.5,'adductors':0.5}),
 'rdl':      (0.85,0.90,{'hams':1.0,'glutes':1.0,'erectors':0.5,'grip':0.2}),
 'legpress': (0.55,0.70,{'quads':1.0,'glutes':0.5}),
 'legcurl':  (0.20,0.25,{'hams':1.0}),
 'calf':     (0.20,0.25,{'calves':1.0}),
}

def session(sets):
    F={}; N=0.0; G=0.0
    for ex,nsets,r,q in sets:
        k,b,cF = EX[ex]
        u=u_of(r+q)
        for m,c in cF.items():
            F[m]=F.get(m,0)+nsets*d0*c*pF(q)*psiR(r)
        N += nsets*n0*k*u*u*pN(q)
        G += nsets*g0*b*pF(q)*psiR(r)
    return F,N,G

def decay(x,h,dt,rho=1.0): return x*np.exp(-rho*np.log(2)/h*dt)

lam_F,lam_N,lam_G = 0.065,0.045,0.030
def suppression(F,N,G,ex):
    k,b,cF = EX[ex]
    tot=sum(cF.values()); w={m:c/tot for m,c in cF.items()}
    Fe=sum(w[m]*F.get(m,0) for m in w)
    e=lam_F*Fe + lam_N*k*N + lam_G*G
    e=min(max(e,0),0.25)
    return Fe, 1-np.exp(-e)

def report(label, sets, dt=24.0, ex='squat'):
    F,N,G = session(sets)
    Fd={m:decay(v,30,dt) for m,v in F.items()}
    Nd=decay(N,24,dt); Gd=decay(G,30,dt)
    Fe,s = suppression(Fd,Nd,Gd,ex)
    print(f"{label:38s} F_e={Fe:.3f} N={Nd:.3f} G={Gd:.3f}  ->  {s*100:5.2f}%")

ordinary = [('squat',4,5,2),('rdl',3,8,2),('legpress',3,10,1),('legcurl',3,12,1),('calf',4,12,0)]
failure  = [('squat',4,5,0),('rdl',3,8,0),('legpress',3,10,0),('legcurl',3,12,0),('calf',4,12,0)]
light    = [('squat',2,5,4),('legpress',2,10,4),('legcurl',2,12,4)]

print("=== 24 h after session (rho=1) ===")
report("ordinary hard lower session", ordinary)
report("failure-heavy lower session", failure)
report("deload session", light)

print("\n=== fresh: 96 h after a deload session ===")
report("post-deload, 96 h", light, dt=96)

print("\n=== overload block peak: 3 hard sessions 48/24/2 h ago ===")
F,N,G={},0,0
for age in (48,24,2):
    f,n,g = session(ordinary if age!=24 else failure)
    for m,v in f.items(): F[m]=F.get(m,0)+decay(v,30,age)
    N+=decay(n,24,age); G+=decay(g,30,age)
Fe,s = suppression(F,N,G,'squat')
print(f"{'overload peak (stacked)':38s} F_e={Fe:.3f} N={N:.3f} G={G:.3f}  ->  {s*100:5.2f}%")

print("\n=== realistic multi-session states ===")
def stacked(events, ex='squat'):
    F,N,G={},0.0,0.0
    for age,sets in events:
        f,n,g = session(sets)
        for m,v in f.items(): F[m]=F.get(m,0)+decay(v,30,age)
        N+=decay(n,24,age); G+=decay(g,30,age)
    Fe,s = suppression(F,N,G,ex)
    return Fe,N,G,s

hi_vol = [('squat',5,6,1),('rdl',4,8,1),('legpress',4,10,1),('legcurl',4,12,1),('calf',4,12,0)]
cases = [
 ("ordinary: 1 hard session 24h ago",      [(24,ordinary)]),
 ("ordinary week: 72h + 24h ago",          [(72,ordinary),(24,ordinary)]),
 ("failure block: 72h + 24h, all RIR0",    [(72,failure),(24,failure)]),
 ("overload block: 96/72/48/24h hi-vol",   [(96,hi_vol),(72,hi_vol),(48,hi_vol),(24,hi_vol)]),
 ("deload week: 96h + 48h light",          [(96,light),(48,light)]),
]
for lab,ev in cases:
    Fe,N,G,s = stacked(ev)
    print(f"{lab:42s} F_e={Fe:.3f} N={N:.3f} G={G:.3f}  ->  {s*100:5.2f}%")

print("\n=== upper body (bench) ===")
EX['bench']=(0.75,0.55,{'chest':1.0,'tris':0.5,'antdelts':0.5})
EX['row']  =(0.65,0.55,{'lats':1.0,'upperback':1.0,'biceps':0.5,'grip':0.2})
EX['ohp']  =(0.70,0.55,{'antdelts':1.0,'tris':0.5,'latdelts':0.5})
EX['lat_raise']=(0.20,0.25,{'latdelts':1.0})
upper = [('bench',4,6,2),('row',4,10,2),('ohp',3,8,1),('lat_raise',4,15,0)]
upper_fail = [('bench',4,6,0),('row',4,10,0),('ohp',3,8,0),('lat_raise',4,15,0)]
for lab,ev in [("upper: 1 hard session 24h ago",[(24,upper)]),
               ("upper failure: 24h ago",       [(24,upper_fail)])]:
    Fe,N,G,s = stacked(ev,'bench')
    print(f"{lab:42s} F_e={Fe:.3f} N={N:.3f} G={G:.3f}  ->  {s*100:5.2f}%")
