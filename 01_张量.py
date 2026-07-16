import torch
import numpy as np

def dm01():
    t1 = torch.ones(size=(3,3))
def dm01():
    t1 = torch.ones(size=(3,3))
    print(t1)
    print(t1.dtype)

    t2 = torch.ones(size=(3,4),dtype=torch.int32)
    print(t2)
    print(t2.dtype)
    t3 = torch.tensor([1,2,3,4,5,6])
    print(t3.shape)
    t4 = torch.ones_like(input=t3)
    print(t4)
    print(t4.dtype)



def dm02():
    t1 = torch.zeros(size=(3,3))
    print(t1)
    print(t1.dtype)
    t1 = torch.tensor([1,2,3,4,5,6])
    print(t1)
    print(t1.dtype)
    t2 = torch.zeros_like(input=t1)
    print(t2)
    print(t2.dtype)


def dm03():
    t1 = torch.full(size=(3,3),fill_value=5)
    print(t1)
    print(t1.dtype)


if __name__ == '__main__':
   # dm01()
   # dm02()
   #12345656
   dm03()