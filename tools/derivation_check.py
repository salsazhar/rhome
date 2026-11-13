"""Check the derived-coefficient rules against MODEL.tex's documented ranges.

MODEL.tex gives target bands for compoundness and systemic cost by exercise
class. The derivation for user-created exercises must land inside them, or it
would assign a user's new movement a cost the model considers implausible.
"""
import math

MU = {  # relative muscle mass weights
 'quads':1.00,'glutes':0.90,'hams':0.70,'lats':0.70,'erectors':0.55,'adductors':0.50,
 'chest':0.60,'upper_back':0.55,'abs':0.35,'calves':0.25,'triceps':0.22,'biceps':0.15,
 'ant_delts':0.20,'lat_delts':0.12,'post_delts':0.12,'forearms':0.10}

K_EQUIP = {'barbell':0.72,'bodyweight':0.60,'dumbbell':0.58,'machine':0.42,'cable':0.34}
D_PATTERN = {'squat':0.12,'hinge':0.12,'v_press':0.04,'h_press':0.04,
             'v_pull':0.04,'h_pull':0.04,'lunge':0.00,'isolation':-0.28}

B_PATTERN = {'squat':0.72,'hinge':0.75,'lunge':0.62,'v_press':0.48,'h_press':0.42,
             'v_pull':0.48,'h_pull':0.48,'isolation':0.18}
B_EQUIP = {'barbell':0.10,'bodyweight':0.05,'dumbbell':0.04,'cable':-0.04,'machine':-0.06}

def derive_b(cS, equip, pattern):
    """Systemic cost: driven by pattern and support, adjusted by recruited mass.

    Mass alone is a poor predictor. A leg extension recruits the quads but is
    seated and braced; a squat recruits the same muscle at whole-body cost.
    Pattern and equipment carry the postural demand; mass modulates it.
    """
    S = sum(w*MU[m] for m,w in cS.items())
    b = B_PATTERN[pattern] + B_EQUIP[equip] + 0.10*min(1.0, S/3.0)
    return min(max(b, 0.20), 1.00), S

def derive_k(equip, pattern, n_primary):
    return min(max(K_EQUIP[equip] + D_PATTERN[pattern] + 0.06*(n_primary-1), 0.15), 1.00)

# name: (equip, pattern, cS weights, n_primary, kappa band, b band)
EX = {
 'Back squat':      ('barbell','squat',{'quads':1.0,'glutes':1.0,'hams':0.5,'erectors':0.5,'adductors':0.5},2,(0.80,1.00),(0.80,1.00)),
 'Deadlift':        ('barbell','hinge',{'hams':1.0,'glutes':1.0,'erectors':1.0,'lats':0.5,'quads':0.5},3,(0.80,1.00),(0.80,1.00)),
 'RDL':             ('barbell','hinge',{'hams':1.0,'glutes':1.0,'erectors':0.5},2,(0.80,1.00),(0.80,1.00)),
 'Bench press':     ('barbell','h_press',{'chest':1.0,'ant_delts':0.5,'triceps':0.5},1,(0.65,0.85),(0.45,0.65)),
 'Overhead press':  ('barbell','v_press',{'ant_delts':1.0,'triceps':0.5,'lat_delts':0.5},1,(0.65,0.85),(0.45,0.65)),
 'Pull-up':         ('bodyweight','v_pull',{'lats':1.0,'upper_back':1.0,'biceps':0.5},2,(0.65,0.85),(0.45,0.65)),
 'Weighted dip':    ('bodyweight','h_press',{'chest':1.0,'triceps':1.0,'ant_delts':0.5},2,(0.65,0.85),(0.45,0.65)),
 'Leg press':       ('machine','squat',{'quads':1.0,'glutes':0.5},1,(0.45,0.65),(0.65,0.85)),
 'Chest-supp. row': ('machine','h_pull',{'lats':1.0,'upper_back':1.0,'biceps':0.5},2,(0.45,0.65),(0.45,0.65)),
 'Bulgarian split': ('dumbbell','lunge',{'quads':1.0,'glutes':1.0,'hams':0.5},2,(0.45,0.85),(0.65,0.85)),
 'Lateral raise':   ('dumbbell','isolation',{'lat_delts':1.0},1,(0.15,0.30),(0.20,0.35)),
 'DB curl':         ('dumbbell','isolation',{'biceps':1.0,'forearms':0.5},1,(0.15,0.30),(0.20,0.35)),
 'Pressdown':       ('cable','isolation',{'triceps':1.0},1,(0.15,0.30),(0.20,0.35)),
 'Leg extension':   ('machine','isolation',{'quads':1.0},1,(0.15,0.30),(0.20,0.35)),
 'Leg curl':        ('machine','isolation',{'hams':1.0},1,(0.15,0.30),(0.20,0.35)),
 'Calf raise':      ('machine','isolation',{'calves':1.0},1,(0.15,0.30),(0.20,0.35)),
 'Cable crunch':    ('cable','isolation',{'abs':1.0},1,(0.15,0.30),(0.20,0.35)),
 'Hanging leg raise':('bodyweight','isolation',{'abs':1.0,'forearms':0.5},1,(0.15,0.35),(0.20,0.40)),
}

print(f"{'exercise':20s} {'kappa':>6s} {'band':>12s} {'':3s} {'b':>5s} {'band':>12s} {'':3s} {'sum':>5s}")
fails=0
for name,(eq,pat,cS,npri,kb,bb) in EX.items():
    k = derive_k(eq,pat,npri); b,S = derive_b(cS,eq,pat)
    ok_k = kb[0]-1e-9 <= k <= kb[1]+1e-9
    ok_b = bb[0]-1e-9 <= b <= bb[1]+1e-9
    fails += (not ok_k) + (not ok_b)
    print(f"{name:20s} {k:6.2f} [{kb[0]:.2f},{kb[1]:.2f}] {'ok' if ok_k else 'FAIL':>3s} "
          f"{b:5.2f} [{bb[0]:.2f},{bb[1]:.2f}] {'ok' if ok_b else 'FAIL':>3s} {S:5.2f}")
print(f"\n{len(EX)*2-fails}/{len(EX)*2} coefficients inside documented bands")
