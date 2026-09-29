"""Persistent per-fish observations; estimates never replace screen checks."""
from pathlib import Path
from statistics import mean,median
import json
import math
import time

from fish_catalog import BY_ID,COLORS


class TimingStore:
    def __init__(self,path):
        self.path=Path(path)
        self.data={'version':1,'fish':{}}
        self.reload()

    def reload(self):
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text())
                if data.get('version')==1 and isinstance(data.get('fish'),dict):self.data=data
            except (OSError,ValueError,TypeError):
                # Do not fabricate measurements from a damaged file.
                pass

    def record(self,fish_id,seconds,uncertainty=0,color=None):
        if fish_id not in BY_ID or not math.isfinite(seconds) or not 1<=seconds<=180:
            return False
        item=self.data['fish'].setdefault(fish_id,{'samples':[],'count':0})
        item['samples']=(item['samples']+[round(seconds,3)])[-40:]
        item['count']+=1
        item['last_uncertainty_seconds']=round(max(0,uncertainty),3)
        if color in COLORS:
            item['observed_color']=color
        item['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data,ensure_ascii=False,indent=2))
        temporary.replace(self.path)
        return True

    def summary(self,fish_id):
        item=self.data['fish'].get(fish_id,{})
        samples=item.get('samples',[])
        if not samples:return {'count':0,'median_seconds':None,'mean_seconds':None,'last_seconds':None}
        return {'count':item.get('count',len(samples)), 'median_seconds':round(median(samples),2),
                'mean_seconds':round(mean(samples),2),'last_seconds':samples[-1],
                'min_seconds':min(samples),'max_seconds':max(samples),
                'last_uncertainty_seconds':item.get('last_uncertainty_seconds',0)}

    def estimate(self,fish_id):
        measured=self.summary(fish_id)['median_seconds']
        return measured if measured is not None else (BY_ID[fish_id].base_seconds if fish_id in BY_ID else None)

    def color(self,fish_id):
        fish=BY_ID.get(fish_id)
        observed=self.data['fish'].get(fish_id,{}).get('observed_color')
        return (fish.color if fish else None) or (observed if observed in COLORS else None)

    def all_summaries(self):
        return {fish_id:self.summary(fish_id) for fish_id in BY_ID}
