"""Add the original Italian letter head to the Nyra INT8 graph offline."""
import argparse
import hashlib
from pathlib import Path
import zipfile

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

# Members of pytorch_model.bin from the pinned Italian foundation revision.
WEIGHT = ('94879813971456', 'a21e4c9395528f48682ce94d76fc874f14e4aebc5a0c12b0da7c157a93e412b6')
BIAS = ('94880238153120', '2e9cea4e3891e9ef6f2813b512bf53a07308c1961a84c8dc3fa6ae10da1e0ce2')


def tensor(archive, member):
    key, digest = member
    raw = archive.read('archive/data/' + key)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Unexpected Italian foundation tensor')
    return np.frombuffer(raw, dtype='<f4')


def export(base, checkpoint, destination):
    if destination.exists():
        raise FileExistsError(destination)
    if hashlib.sha256(base.read_bytes()).hexdigest() != '90cf72e4664ae15817c0b1323e01c0ec66b915fa9806914cb8c1def344f168ff':
        raise ValueError('Unexpected base verifier')
    with zipfile.ZipFile(checkpoint) as archive:
        weight = tensor(archive, WEIGHT).reshape(44, 1024).T.copy()
        bias = tensor(archive, BIAS)
    model = onnx.load(base)
    hidden = next(n.input[1] for n in model.graph.node
                  if n.name == '/MatMul' and n.input[0] == 'pool')
    model.graph.initializer.extend([numpy_helper.from_array(weight, 'ctc_weight'),
                                    numpy_helper.from_array(bias, 'ctc_bias')])
    model.graph.node.extend([helper.make_node('MatMul', [hidden, 'ctc_weight'], ['ctc_raw']),
                             helper.make_node('Add', ['ctc_raw', 'ctc_bias'], ['ctc_logits'])])
    model.graph.output.append(helper.make_tensor_value_info('ctc_logits', TensorProto.FLOAT, [1, None, 44]))
    onnx.checker.check_model(model)
    onnx.save(model, destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('base', 'checkpoint', 'destination'):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    export(args.base, args.checkpoint, args.destination)
