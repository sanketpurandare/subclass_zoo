import functools
import torch

import torch
from torch._C import device
import torch.nn as nn
from torch.return_types import _fake_quantize_per_tensor_affine_cachemask_tensor_qparams
from torch.utils._pytree import tree_map, tree_flatten
from typing import List, Any
from numbers import Number
from collections import defaultdict
from torch.utils._python_dispatch import push_torch_dispatch_mode, TorchDispatchMode
from torch._utils import (
    _get_all_device_indices,
    _get_available_device_type,
    _get_device_index,
    _get_devices_properties
)
aten = torch.ops.aten

class DataParallelTensor(torch.Tensor):
    elem: List[torch.Tensor]
    device_ids: List[int] = _get_all_device_indices()
    __slots__ = ["elem"]

    @staticmethod
    def __new__(cls, elem, func=None, replicate=False):
        
        if(replicate):
            r = torch.Tensor._make_wrapper_subclass(
            cls,
            elem.size(),
            strides=elem.stride(),
            storage_offset=elem.storage_offset(),
            # TODO: clone storage aliasing
            dtype=elem.dtype,
            layout=elem.layout,
            requires_grad=elem.requires_grad,
        )
            r.elem = []
            with torch.no_grad():
                for device_id in r.device_ids:
                    t:torch.Tensor = elem.to(device = device_id)
                    t.requires_grad = elem.requires_grad
                    r.elem.append(t)
                    t = None
        else:
            assert (isinstance(elem, list))
            r = torch.Tensor._make_wrapper_subclass(
            cls,
            elem[0].size(),
            strides=elem[0].stride(),
            storage_offset=elem[0].storage_offset(),
            # TODO: clone storage aliasing
            dtype=elem[0].dtype,
            layout=elem[0].layout,
            requires_grad=elem[0].requires_grad,
            )
            pos = 0
            for t, d_id in zip(elem, r.device_ids):
                if(t.device != device(d_id)):
                    elem[pos] = t.to(device = d_id)
                pos += 1          
            r.elem = elem

        return r

    def __repr__(self):
        if self.grad_fn:
            return f"DataParallelTensor({self.elem}, grad_fn={self.grad_fn})"
        return f"DataParallelTensor({self.elem})"

    @classmethod
    def __torch_dispatch__(cls, func, types, args=(), kwargs=None):
        def unwrap_with_position(pos):
            def get_element(e):
                return e.elem[pos] if isinstance(e, DataParallelTensor) else e
            return get_element

        outs = []
        for pos in range(len(cls.device_ids)):
            # import pdb
            # if(func == aten.mul.Tensor):
            #     pdb.set_trace()
            outs.append(func(*tree_map(unwrap_with_position(pos), args), **tree_map(unwrap_with_position(pos), kwargs)))
        # outs = func(*tree_map(unwrap, args), **tree_map(unwrap, kwargs))

        def get_element_type (lis):
            assert(isinstance(lis, list))
            return type(lis[0])

        def wrap(e, func):
            if e is None:
                return torch.empty(())
            elem_type = get_element_type(e)

            if(elem_type == torch.Tensor):
                return DataParallelTensor(outs, func)
            elif(elem_type == list):
                return list(DataParallelTensor(list(t), func) for t in zip(*e))
            elif(elem_type == tuple):
                return tuple(DataParallelTensor(list(t), func)for t in zip(*e))

        #outs = tree_map(wrap, outs)
        outs = wrap(outs, func)
        return outs

print(_get_all_device_indices())
test_tensor = torch.randn(5, device = 'cuda', requires_grad=True)
dp_tensor = DataParallelTensor(test_tensor, None ,True)
res_tensor = dp_tensor.cos().cos().sum()
print(res_tensor)
test_tensor.to(device='cuda')
res_tensor.backward()
    
