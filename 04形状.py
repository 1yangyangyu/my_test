import torch
torch.manual_seed(1)
t1=torch.randint(0,3,(5,6))
print(t1)
print(t1.size())
print(t1.size(0))
print(t1.size(1))
print(t1.size(-1))

t2 = t1.reshape(5,-1)
print(t2)
print(t2.size())