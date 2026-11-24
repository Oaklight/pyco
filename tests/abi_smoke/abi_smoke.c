#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject *
abi_smoke_ping(PyObject *self, PyObject *args)
{
    long value;

    (void)self;
    if (!PyArg_ParseTuple(args, "l", &value)) {
        return NULL;
    }
    return PyLong_FromLong(value + 1);
}

static PyMethodDef abi_smoke_methods[] = {
    {"ping", abi_smoke_ping, METH_VARARGS, "Return the argument plus one."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef abi_smoke_module = {
    PyModuleDef_HEAD_INIT,
    "abi_smoke",
    "Small C extension used to verify the public CPython ABI.",
    -1,
    abi_smoke_methods
};

PyMODINIT_FUNC
PyInit_abi_smoke(void)
{
    return PyModule_Create(&abi_smoke_module);
}
