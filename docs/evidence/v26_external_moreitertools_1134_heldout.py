"""Frozen before inference; withheld from model proposal and public feedback."""
from decimal import Decimal
from fractions import Fraction
from statistics import median, mean
import unittest
import more_itertools as mi

def windows(data,n):
 for stop in range(1,len(data)+1):
  yield data[max(0,stop-n):stop]

class HiddenRunningStatistics(unittest.TestCase):
 def test_empty(self):
  for fn in [mi.running_min,mi.running_max,mi.running_mean,mi.running_statistics]:
   with self.subTest(fn=fn.__name__):
    self.assertEqual(list(fn([])),[])
 def test_min_max_varied_windows(self):
  data=[12,5,9,3,7,2,8,1]
  for k in range(1,6):
   self.assertEqual(list(mi.running_min(data,maxlen=k)),
                    [min(w) for w in windows(data,k)])
   self.assertEqual(list(mi.running_max(data,maxlen=k)),
                    [max(w) for w in windows(data,k)])
 def test_mean_varied_windows(self):
  data=[1,7,3,12,0,6,9]
  for k in range(1,5):
   got=list(mi.running_mean(data,maxlen=k))
   exp=[mean(w) for w in windows(data,k)]
   for a,b in zip(got,exp):self.assertAlmostEqual(a,b)
 def test_statistics_window_and_even_median(self):
  data=[9,3,7,0,8,1,6]
  for k in (1,2,3,4,10):
   vals=list(mi.running_statistics(data,maxlen=k))
   for i,(v,window) in enumerate(zip(vals,windows(data,k))):
    self.assertEqual(v.size,len(window))
    self.assertEqual(v.minimum,min(window))
    self.assertEqual(v.maximum,max(window))
    self.assertEqual(v.median,median(window))
    self.assertAlmostEqual(v.mean,mean(window))
 def test_error_arguments(self):
  with self.assertRaises(TypeError):mi.running_statistics(None)
  for fn in [mi.running_min,mi.running_max,mi.running_mean,mi.running_statistics]:
   with self.assertRaises(ValueError):list(fn([1,2,3],maxlen=-1))
 def test_numeric_types(self):
  for ctor in (int,float,Fraction,Decimal):
   x=list(map(ctor,[3,1,5,2]))
   self.assertEqual(len(list(mi.running_statistics(x,maxlen=2))),4)
 def test_complex_mean_supported(self):
  data=[3+4j,5-1j,4+3j]
  self.assertEqual(list(mi.running_mean(data)),
                   [3+4j,4+1.5j,4+2j])
 def test_stats_behavior(self):
  st=mi.Stats(size=2,minimum=1,median=1.5,maximum=2,mean=1.5)
  self.assertEqual(st,mi.Stats(size=2,minimum=1,median=1.5,maximum=2,mean=1.5))
  hash(st)
  with self.assertRaises(AttributeError):st.size=9
  with self.assertRaises(TypeError):len(st)
  with self.assertRaises(TypeError):iter(st)
  with self.assertRaises(TypeError):st[0]
 def test_large_window_same_as_unbounded(self):
  x=[4,3,7,0,8,1,6]
  for fn in [mi.running_min,mi.running_max,mi.running_mean,mi.running_statistics]:
   self.assertEqual(list(fn(x,maxlen=99)),list(fn(x)))
 def test_lazy_generator(self):
  consumed=[]
  def numbers():
   for v in [5,2,9]:
    consumed.append(v)
    yield v
  it=mi.running_statistics(numbers())
  self.assertEqual(consumed,[])
  self.assertEqual(next(it).size,1)
  self.assertEqual(consumed,[5])
