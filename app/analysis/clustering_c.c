#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static PyObject* form_clusters(PyObject* self, PyObject* args) {
    printf("Clustering with C.\n");

    PyArrayObject *cosine_sim;
    int min_samples;
    double threshold;

    if (!PyArg_ParseTuple(args, "O!id", &PyArray_Type, &cosine_sim, &min_samples, &threshold)) {
        return NULL;
    }

    int n = (int)PyArray_DIM(cosine_sim, 0);
    double* data = (double*)PyArray_DATA(cosine_sim);

    // Zero out diagonal
    for (int i = 0; i < n; ++i) {
        data[i * n + i] = 0;
    }

    // Drop everything less than threshold
    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            if (data[i * n + j] < threshold) {
                data[i * n + j] = 0;
            }
        }
    }

    PyObject* clusters = PyList_New(0);
    int* visited = (int*)calloc(n, sizeof(int));
    int* queue = (int*)malloc(n * sizeof(int));

    for (int i = 0; i < n; ++i) {
        if (!visited[i]) {
            int queue_start = 0, queue_end = 0;
            queue[queue_end++] = i;
            visited[i] = 1;

            PyObject* cluster = PySet_New(NULL);

            while (queue_start < queue_end) {
                int current = queue[queue_start++];

                for (int j = 0; j < n; ++j) {
                    if (data[current * n + j] >= threshold && !visited[j]) {
                        queue[queue_end++] = j;
                        visited[j] = 1;
                    }
                }

                PySet_Add(cluster, PyLong_FromLong(current));
            }

            if (PySet_Size(cluster) >= min_samples) {
                PyList_Append(clusters, cluster);
            }
            Py_DECREF(cluster);
        }
    }

    free(visited);
    free(queue);

    return clusters;
}

static PyMethodDef MaudlinlibMethods[] = {
        {"form_clusters", form_clusters, METH_VARARGS, "Form clusters from cosine similarity matrix."},
        {NULL, NULL, 0, NULL}
};

static struct PyModuleDef maudlinlibmodule = {
        PyModuleDef_HEAD_INIT,
        "cluster",
        NULL,
        -1,
        MaudlinlibMethods
};

PyMODINIT_FUNC PyInit_maudlinlib(void) {
    import_array();
    return PyModule_Create(&maudlinlibmodule);
}
