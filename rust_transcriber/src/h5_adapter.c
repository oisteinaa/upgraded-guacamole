/* Narrow read-only HDF5 interface. Handles are closed on every error path. */
#include <hdf5.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
int64_t das_open(const char *path) {
    H5Eset_auto2(H5E_DEFAULT, NULL, NULL);
    return H5Fopen(path, H5F_ACC_RDONLY, H5P_DEFAULT);
}
void das_close(int64_t f) { H5Fclose(f); }
int das_info(int64_t f, const char *name, uint64_t *dims, int *kind) {
    hid_t d = H5Dopen2(f, name, H5P_DEFAULT);
    if (d < 0) return -1;
    hid_t s = H5Dget_space(d), t = H5Dget_type(d);
    int n = H5Sget_simple_extent_ndims(s);
    *kind = H5Tget_class(t);
    if (n >= 0 && n <= 2) { hsize_t sizes[2] = {1,1}; H5Sget_simple_extent_dims(s, sizes, NULL); dims[0]=sizes[0]; dims[1]=sizes[1]; }
    H5Tclose(t); H5Sclose(s); H5Dclose(d);
    return n;
}
int das_read(int64_t f, const char *name, void *out, int integer) {
    hid_t d = H5Dopen2(f, name, H5P_DEFAULT);
    if (d < 0) return -1;
    int result=H5Dread(d, integer ? H5T_NATIVE_INT64 : H5T_NATIVE_DOUBLE, H5S_ALL,H5S_ALL,H5P_DEFAULT,out);
    H5Dclose(d); return result;
}
int das_string(int64_t f, const char *name, char *out, size_t capacity) {
    hid_t d=H5Dopen2(f,name,H5P_DEFAULT);
    if (d<0) return -1;
    hid_t t=H5Dget_type(d), s=H5Dget_space(d);
    int result=-1;
    if (H5Tget_class(t)==H5T_STRING && H5Sget_simple_extent_npoints(s)==1) {
        if (H5Tis_variable_str(t)>0) {
            char *v=NULL;
            if (H5Dread(d,t,H5S_ALL,H5S_ALL,H5P_DEFAULT,&v)>=0 && v) {
                size_t n=strlen(v);
                if(n<capacity) { memcpy(out,v,n+1); result=0; }
                H5free_memory(v);
            }
        } else {
            size_t n=H5Tget_size(t);
            if(n<capacity && H5Dread(d,t,H5S_ALL,H5S_ALL,H5P_DEFAULT,out)>=0) {out[n]=0; result=0;}
        }
    }
    H5Sclose(s); H5Tclose(t); H5Dclose(d); return result;
}
int das_slice(int64_t f, uint64_t row, uint64_t col, uint64_t rows, uint64_t cols, double *out) {
    hid_t d=H5Dopen2(f,"data",H5P_DEFAULT);
    if(d<0) return -1;
    hid_t space=H5Dget_space(d);
    hsize_t start[2]={row,col}, count[2]={rows,cols};
    hid_t mem=H5Screate_simple(2,count,NULL);
    int result=H5Sselect_hyperslab(space,H5S_SELECT_SET,start,NULL,count,NULL);
    if(result>=0) result=H5Dread(d,H5T_NATIVE_DOUBLE,mem,space,H5P_DEFAULT,out);
    H5Sclose(mem); H5Sclose(space); H5Dclose(d); return result;
}
