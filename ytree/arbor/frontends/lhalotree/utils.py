"""
LHaloTree utilities



"""

import warnings
import numpy as np
from numpy.lib.recfunctions import append_fields
import os
import glob


"""Default header data type."""
dtype_header_default = [
    # merger tree pointers
    ('Descendant', 'i4'),
    ('FirstProgenitor', 'i4'),
    ('NextProgenitor', 'i4'),
    ('FirstHaloInFOFgroup', 'i4'),
    ('NextHaloInFOFgroup', 'i4'),
    # properties of halo
    ('Len', 'i4'),
    ('M_Mean200', 'f4'),
    ('Mvir', 'f4'), # for Millennium, Mvir=M_Crit200
    ('M_TopHat', 'f4'),
    ('Pos', 'f4', 3),
    ('Vel', 'f4', 3),
    ('VelDisp', 'f4'),
    ('Vmax', 'f4'),
    ('Spin', 'f4', 3),
    ('MostBoundID', 'i8'),
    # original position in simulation tree files
    ('SnapNum', 'i4'),
    ('FileNr', 'i4'),
    ('SubhaloIndex', 'i4'),
    ('SubHalfMass', 'f4')]
halo_fields = ['Descendant', 'FirstProgenitor', 'NextProgenitor',
               'FirstHaloInFOFgroup', 'NextHaloInFOFgroup']


def read_header_default(filename):
    r"""Reads the default LHaloTree file header.

    Args:
        filename (str): Full path to file that header should be read from.

    Returns:
         tuple (int, np.ndarray): The size of the file header and the number
             of halos in each header.

    """
    with open(filename, 'rb') as fd:
        dtype1 = np.dtype([('ntrees', 'i4'), ('totnhalos', 'i4')])
        x1 = np.fromfile(fd, dtype=dtype1, count=1)
        ntrees = x1['ntrees'][0]
        nhalos = x1['totnhalos'][0]
        dtype2 = np.dtype('i4')
        x2 = np.fromfile(fd, dtype=dtype2, count=ntrees)
        assert(len(x2) == ntrees)
        assert(np.sum(x2) == nhalos)
        header_size = dtype1.itemsize + ntrees*dtype2.itemsize
    return header_size, x2


class LHaloTreeReader(object):
    r"""Class for reading halos from an LHaloTree file.

    Args:
        filename (str): Full path to file that trees should be read from.
        parameters (dict, optional): Dictionary of simulation parameters. If not
            provided, parameters are loaded from parameter_file.
        parameter_file (str, optional): Full path to file that contains
            simulation parameters. If not provided, one with the suffix '.param'
            is searched for in the same directory as the tree file. An IOError
            will be raised if it cannot be found.
        scale_factors (np.ndarray, optional): 1D array of scale factors for each
            snapshot. If not provided, they are loaded form scale_factor_file.
        scale_factor_file (str, optional): Full path to the file containing the
            list of scale factors for each snapshot. If not provided, one with
            the suffix '.a_list' is searched for in the same directory as the
            tree file. An IOError will be raised if it cannot be found.
        header_size (int, optional): The size of the file header. If not
            provided, it will be obtained from read_header_func.
        nhalos_per_tree (np.ndarray, optional): The number of halos in each of
            the ntree trees in the file. If not provided, it will be obtained
            from read_header_func.
        read_header_func (obj, optional): Callable object that takes a filename
            and returns the size of the file header and the number of halos in
            each tree in the file. Defaults to read_header_default.
        item_dtype (obj, optional): np.dtype or object that can be converted
            into a numpy dtype specifying the structure of single halo entries
            in the tree. Defaults to dtype_header_default.
        silent (bool, optional): If True, diagnositic info is not printed.
            Defaults to False.

    Attributes:
        filename (str): Full path to file that trees should be read from.
        fileindex (int): Index of this file in the full set of trees.
        filepattern (str): Glob style pattern that can be used to find other
            files in the full set of trees.
        parameter_file (str): Full path to file that contains simulation
            parameters.
        header_size (int): The size of the file header.
        nhalos_per_tree (np.ndarray): The number of halos in each of the ntree
            trees in the file.
        item_dtype (np.dtype): Data type specifying the structure of single halo
            entries in the tree.
        raw_fields (list): Available fields that are present for each halo based
            on item_dtype.
        add_fields (list): Calculated fields that will be added to trees as they
            are read.
        fields (list): All available fields that are present for each halo.
        filenum (int): Index of this file in the complete set for all trees.
        scale_factor_file (str): Full path to the file containing the list of
            scale factors for each snapshot.

    Raises:
        IOError: If filename is not a valid path.
        IOError: If a parameter_file is not provided or is not a valid path.
        IOError: If a scale_factor_file is not provided and cannot be found.
        IOError: If the file dosn't have the expected number of bytes.

    """

    def __init__(self, filename, parameters=None, parameter_file=None,
                 scale_factors=None, scale_factor_file=None,
                 header_size=None, nhalos_per_tree=None, read_header_func=None,
                 item_dtype=None, silent=False):
        # Files
        self.filename = self._verify_file(filename)
        ext = self.filename.split('.')[-1]
        if ext.isdigit():
            self.fileindex = int(ext)
            self.filepattern = os.path.splitext(self.filename)[0] + ".*"
        else:
            self.fileindex = 0
            self.filepattern = self.filename
        if parameters is not None:
            self._parameters = parameters
        else:
            self.parameter_file = self._verify_file(
                parameter_file, suffix='.param', error_tag='Parameter file',
                silent=silent)
            self._parameters = None
        if scale_factors is not None:
            self._scale_factors = scale_factors
        else:
            self.scale_factor_file = self._verify_file(
                scale_factor_file, suffix='.a_list', error_tag='Scale factor file',
                silent=silent)
            self._scale_factors = None
        # Header info
        if (header_size is None) or (nhalos_per_tree is None):
            if (read_header_func is None):
                read_header_func = read_header_default
            header_size, nhalos_per_tree = read_header_func(filename)
        if (item_dtype is None):
            item_dtype = dtype_header_default
        self.header_size = header_size
        self.nhalos_per_tree = nhalos_per_tree
        self.item_dtype = np.dtype(item_dtype)
        # Fields
        self.raw_fields = list(self.item_dtype.fields.keys())
        self.add_fields = ['desc_uid', 'scale_factor', 'uid',
                           'x', 'y', 'z', 'vx', 'vy', 'vz',
                           'Jx', 'Jy', 'Jz']
        self.fields = self.raw_fields + self.add_fields
        # Check file size
        item_size = self.item_dtype.itemsize
        body_size = self.totnhalos * item_size
        file_size = os.stat(self.filename).st_size
        if body_size != file_size - self.header_size:
            raise IOError(
                ("File is %d bytes, but %d items of size %d " +
                 "with header of %d bytes should be %d bytes total.") \
                 % (file_size, self.totnhalos, item_size,
                    self.header_size, body_size + self.header_size))
        # Read first halo to get file number and check first FoF
        out = self.read_single_halo(0, 0, skip_add_fields=True)
        self.filenum = out['FileNr'][0]
        if (out['SnapNum'][0] + 1) != len(self.scale_factors):
            warnings.warn("First FoF central is in snapshot %d/%d." % (
                out['SnapNum'][0] + 1, len(self.scale_factors)))
        # Compute uids and descids for all trees
        uid = np.int64(self.filenum)
        self.all_uids = np.bitwise_or(uid << 32,
                                      np.arange(self.totnhalos, dtype='int64'))
        desc = self.read_all_lhalotree(as_recarray=True)['Descendant']
        self.all_desc_uids = np.zeros(self.totnhalos, dtype='int64') - 1
        for t in range(self.ntrees):
            idx = self.get_total_index(t)
            uid = self.all_uids[idx]
            pos_flag = (desc[idx] >= 0)
            self.all_desc_uids[idx][pos_flag] = uid[desc[idx][pos_flag]]

    def _verify_file(self, filename, suffix=None, error_tag=None, silent=False):
        r"""Verify that the provided file exists. If it is None, and a suffix
        is provided, the file will be searched for in the same directory as
        self.filename.

        Args:
            filename (str): Full path that should be verified or None if the
                file should be searched for.
            suffix (str, optional): Suffix that should be used to search for a
                file if filename is None or dosn't exist. Defaults to None and
                no search is performed.
            error_tag (str, optional): Tag to use for error message in case
                where file dosn't exist. Defaults to None and 'File' is used.
            silent (bool, optional): If True, messages about located files are
                not printed. Defaults to False.

        Returns:
            str: Verified full path to the file.

        Raises:
            IOError: If filename is not a valid path and suffix is None.
            IOError: If a filename matching suffix cannot be located.

        """
        if error_tag is None:
            error_tag = 'File'
        if (filename is None) or (not os.path.isfile(filename)):
            if suffix is None:
                raise IOError("%s dosn't exist: %s" % (error_tag, filename))
            pattern = os.path.join(os.path.dirname(self.filename), '*' + suffix)
            files = glob.glob(pattern)
            if len(files) == 0:
                raise IOError("%s could not be located matching: %s" % (
                    error_tag, pattern))
            else:
                filename = files[0]
                if not silent:
                    print("Using %s found at %s" % (error_tag.lower(), filename))
        return filename

    @property
    def totnhalos(self):
        r"""int: Total number of halos in this file."""
        return np.sum(self.nhalos_per_tree)

    @property
    def ntrees(self):
        r"""int: Number of trees in this file."""
        return len(self.nhalos_per_tree)

    @property
    def parameters(self):
        r"""dict: Key/value pairs read from the parameter file."""
        if self._parameters is None:
            self._parameters = dict()
            with open(self.parameter_file, 'r') as fd:
                for line in fd:
                    line_strip = line.strip()
                    if len(line_strip) == 0:
                        continue
                    line_vars = line_strip.split()
                    if len(line_vars) != 2:
                        continue
                    self._parameters[line_vars[0]] = line_vars[1]
        return self._parameters

    @property
    def hubble_constant(self):
        r"""float: Hubble constants."""
        return float(self.parameters['HubbleParam'])

    @property
    def omega_matter(self):
        r"""float: Matter energy density."""
        return float(self.parameters['Omega0'])

    @property
    def omega_lambda(self):
        r"""float: Dark matter energy density."""
        return float(self.parameters['OmegaLambda'])

    @property
    def box_size(self):
        r"""float: Size of periodic boundaries."""
        return float(self.parameters['BoxSize'])

    @property
    def periodic(self):
        r"""bool: Does the simulation have periodic boundaries or not."""
        return bool(int(self.parameters['PeriodicBoundariesOn']))

    @property
    def comoving(self):
        r"""bool: Is the simulation in comoving units."""
        return bool(int(self.parameters['ComovingIntegrationOn']))

    @property
    def units_vel(self):
        r"""str: Units of velocity."""
        # out = "%s cm/s" % self.parameters['UnitVelocity_in_cm_per_s']
        u_cms = float(self.parameters['UnitVelocity_in_cm_per_s'])
        out = "%f*km/s" % (u_cms/1e5)
        # TODO: Does this need adjusted for comoving?
        return out

    @property
    def units_len(self):
        r"""str: Units of length."""
        # out = "%s cm" % self.parameters['UnitLength_in_cm']
        u_cm = float(self.parameters['UnitLength_in_cm'])
        out = "%f*kpc" % (u_cm/3.085678e21)
        if self.comoving:
            out += "/h"
        return out

    @property
    def units_mass(self):
        r"""str: Units of mass."""
        # out = "%s g" % self.parameters['UnitMass_in_g']
        u_g = float(self.parameters['UnitMass_in_g'])
        out = "%f*Msun" % (u_g/1.989e33)
        if self.comoving:
            out += "/h"
        return out

    @property
    def scale_factors(self):
        r"""np.ndarray: Array of scale factors at each snapshot."""
        if self._scale_factors is None:
            self._scale_factors = np.fromfile(self.scale_factor_file, sep='\n')
        return self._scale_factors

    def get_total_index(self, treenum, halonum=None):
        r"""Get the slice that selects halos in a single tree.

        Args:
            treenum (int): Index of the tree to get the slice for.
            halonum (int, optional): Index of a halo within the tree to
                get the total index for in the file. Defaults to None and
                the slice for the entire tree is returned.

        Returns:
            slice, int: Slice of all halos for this tree.

        """
        start = np.sum(self.nhalos_per_tree[:treenum])
        if halonum is None:
            return slice(start, start + self.nhalos_per_tree[treenum])
        else:
            return start + halonum

    def get_lhalotree_offset(self, treenum):
        r"""Get the offset in bytes of a tree from the beginning of the file.

        Args:
            treenum (int): Index of the tree to compute the offset of.

        Returns:
            int: Number of bytes from beginning of the file to the start of the
                requested tree.

        """
        offset = self.header_size + (np.sum(self.nhalos_per_tree[:treenum]) *
                                     self.item_dtype.itemsize)
        return offset

    def get_halo_offset(self, treenum, halonum):
        r"""Get the offset in bytes of a halo from the beginning of the file.

        Args:
            treenum (int): Index of the tree that requested halo is in.
            halonum (int): Index of the requested in halo in the tree.

        Returns:
            int: Number of bytes from beginning of the file to the start of the
                requested halo.

        """
        offset = self.get_lhalotree_offset(treenum)
        offset += halonum * self.item_dtype.itemsize
        return offset

    def get_halo_uid(self, treenum, halonum=None):
        r"""Get a unique ID for a certain halo(s) in the tree. Currently, this
        is a combination of the FileNr and the index of the halo in the file
        created by concatenating bytes.
        
        Args:
            treenum (int): Index of the tree that requested halo is in.
            halonum (int, optional): Index or array of the requested halo(s) in
               the tree. If not provided, uids for every halo in the tree are
               returned.

        Returns:
            int, np.ndarray: Unique ID(s) for the requested halo(s).

        """
        idx = self.get_total_index(treenum, halonum)
        # if halonum is None:
        #     halonum = np.arange(self.nhalos_per_tree[treenum], dtype='int64')
        # ihalo = np.int64(np.sum(self.nhalos_per_tree[:treenum])) + halonum
        # uid = np.int64(self.filenum)
        # return np.bitwise_or(uid << 32, ihalo)
        return self.all_uids[idx]

    def get_halo_desc_uid(self, treenum, halonum=None):
        r"""Get a unique ID for a certain halo(s) descendant(s) in the tree.
        
        Args:
            treenum (int): Index of the tree that requested halo is in.
            halonum (int, optional): Index or array of the requested halo(s) in
               the tree. If not provided, uids for every halo in the tree are
               returned.

        Returns:
            int, np.ndarray: Unique ID(s) for the requested halo(s) descendant(s).

        """
        idx = self.get_total_index(treenum, halonum)
        return self.all_desc_uids[idx]

    def get_lhalotree_uid(self, treenum):
        r"""Get a unique ID for this tree.
        
        Args:
            treenum (int): Index of the tree to get a unique ID for.

        Returns:
            int: A unique ID for this tree.

        """
        return self.get_halo_uid(treenum, 0)

    def get_lhalotree_desc_uid(self, treenum):
        r"""Get a unique ID for the descendant of this tree's root.
        
        Args:
            treenum (int): Index of the tree to get a descendent for.

        Returns:
            int: A unique ID for this tree's root's descendant.

        """
        return self.get_halo_desc_uid(treenum, 0)

    def get_all_uid(self):
        r"""Return unique IDs for every halo in the file.

        Returns:
            np.ndarray: Unique IDs for every halo in the file.

        """
        return self.all_uids

    def get_all_desc_uid(self):
        r"""Return unique IDs for every halo's descendant in the file.

        Returns:
            np.ndarray: Unique IDs for the descendants of every halo in the file.

        """
        return self.all_desc_uids

    def read_single_halo(self, treenum, halonum, fd=None, skip_add_fields=False,
                         as_recarray=False):
        r"""Read a single halo entry from a tree in the file.

        Args:
            treenum (int): Index of the tree that contains the requested halo.
            halonum (int): Index of the halo within its tree.
            fd (file, optional): Open file identifier. If not provided, the file
                is opened for the read and then closed.
            skip_add_fields (bool, optional): If True, the calculated fields
                will not be added or checked for. Defaults to False.
            as_recarray (bool, optional): If True, the returned data is a
                structured array with fields for the halo. Otherwise, the data
                is a dictionary of arrays. Defaults to False.

        Returns:
            np.ndarray, dict: Dictionary or single element structured array with
                fields for the corresponding halo.

        """
        # Open file as necessary
        opened = False
        if (fd is None) or (fd.name != self.filename):
            if fd is not None:
                warnings.warn("Passed file handler is not for this file. " +
                              "Opening a new file.")
            fd_new = open(self.filename, 'rb')
            opened = True
        else:
            fd_new = fd
        # Seek to halo location and read
        offset = self.get_halo_offset(treenum, halonum)
        fd_new.seek(offset, os.SEEK_SET)
        out_ra = np.fromfile(fd_new, dtype=self.item_dtype, count=1)
        if opened:
            fd_new.close()
        # Convert to dictionary
        if as_recarray:
            out = out_ra
        else:
            out = {k: out_ra[k] for k in out_ra.dtype.fields.keys()}
        # Validate
        self.validate_halo(out)
        # Add fields
        if not skip_add_fields:
            out = self.add_computed_fields(treenum, out, halonum=halonum)
        return out

    def read_single_lhalotree(self, treenum, fd=None, as_recarray=False):
        r"""Read a single lhalotree from the file.

        Args:
            treenum (int): Index of the tree that should be read from the file.
                (starts at 0)
            fd (file, optional): Open file identifier. If not provided, the file
                is opened for the read and then closed.
            as_recarray (bool, optional): If True, the returned data is a
                structured array with fields for each halo. Otherwise, the data
                is a dictionary of arrays. Defaults to False.

        Returns:
            dict, np.ndarray: Dictionary or structured array with fields for
                each halo in the corresponding tree.

        """
        # Open file as necessary
        opened = False
        if (fd is None) or (fd.name != self.filename):
            if fd is not None:
                warnings.warn("Passed file handler is not for this file. " +
                              "Opening a new file.")
            fd_new = open(self.filename, 'rb')
            opened = True
        else:
            fd_new = fd
        # Seek to proper location and read file
        offset = self.get_lhalotree_offset(treenum)
        fd_new.seek(offset, os.SEEK_SET)
        out_ra = np.fromfile(fd_new, dtype=self.item_dtype,
                             count=self.nhalos_per_tree[treenum])
        if opened:
            fd_new.close()
        # Convert to dictionary
        if as_recarray:
            out = out_ra
        else:
            out = {k: out_ra[k] for k in out_ra.dtype.fields.keys()}
        # Validate
        self.validate_tree(treenum, out)
        # Add fields
        out = self.add_computed_fields(treenum, out)
        return out

    def read_all_lhalotree(self, fd=None, as_recarray=False):
        r"""Read a all lhalotrees from the file.

        Args:
            fd (file, optional): Open file identifier. If not provided, the file
                is opened for the read and then closed.
            as_recarray (bool, optional): If True, the returned data is a
                structured array with fields for each halo. Otherwise, the data
                is a dictionary of arrays. Defaults to False.

        Returns:
            dict, np.ndarray: Dictionary or structured array with fields for
                each halo in the file.

        """
        # Open file as necessary
        opened = False
        if (fd is None) or (fd.name != self.filename):
            if fd is not None:
                warnings.warn("Passed file handler is not for this file. " +
                              "Opening a new file.")
            fd_new = open(self.filename, 'rb')
            opened = True
        else:
            fd_new = fd
        # Seek to proper location and read file
        offset = self.get_lhalotree_offset(0)
        fd_new.seek(offset, os.SEEK_SET)
        out_ra = np.fromfile(fd_new, dtype=self.item_dtype,
                             count=np.sum(self.nhalos_per_tree))
        if opened:
            fd_new.close()
        # Convert to dictionary
        if as_recarray:
            out = out_ra
        else:
            out = {k: out_ra[k] for k in out_ra.dtype.fields.keys()}
        return out

    def add_computed_fields(self, treenum, tree, halonum=None):
        r"""Add computed fields to the numpy array.

        Args:
            treenum (int): Index of tree in file.
            tree (np.ndarray): Structured data for each halo in the tree.
            halonum (int, optional): Index of halo in the tree if tree contains
                a single halo.

        Returns:
            np.ndarray: Structured data for each halo in the tree with added
                fields.

        """
        try:
            nhalos = len(tree['SnapNum'])
        except AttributeError:
            nhalos = len(tree)
        if nhalos != self.nhalos_per_tree[treenum]:
            assert(nhalos == 1)
            assert(halonum is not None)
        else:
            halonum = None
        # Unique ID for each halo in tree
        all_uids = self.get_halo_uid(treenum)
        if halonum is not None:
            uid = np.array([all_uids[halonum]], dtype='i8')
        else:
            uid = all_uids
        # Descendant unique ID
        flag_pos = (tree['Descendant'] > -1)
        desc_uid = np.zeros(nhalos, dtype='i8') - 1
        desc_uid[flag_pos] = all_uids[tree['Descendant'][flag_pos]]
        # Scale factors
        scale_factor = self.scale_factors[tree['SnapNum']]
        # Position x, y, z
        x = tree['Pos'][:, 0]
        y = tree['Pos'][:, 1]
        z = tree['Pos'][:, 2]
        # Velocity x, y, z
        vx = tree['Vel'][:, 0]
        vy = tree['Vel'][:, 1]
        vz = tree['Vel'][:, 2]
        # Spin x, y, z
        Jx = tree['Spin'][:, 0]
        Jy = tree['Spin'][:, 1]
        Jz = tree['Spin'][:, 2]
        # Add new fields
        new_fields = dict(uid=uid, desc_uid=desc_uid, scale_factor=scale_factor,
                          x=x, y=y, z=z, vx=vx, vy=vy, vz=vz, Jx=Jx, Jy=Jy, Jz=Jz)
        try:
            out = tree
            out.update(**new_fields)
        except AttributeError:
            out = append_fields(tree, new_fields.keys(), new_fields.values())
        self.validate_fields(out)
        return out

    def validate_tree(self, treenum, tree):
        r"""Check that the tree conforms to expectation.

        Args:
            treenum (int): Index of the tree being validated in the file.
            tree (np.ndarray): Structured array of information for halos in a
                tree.

        Raises:
            AssertionError: If the tree does not have the expected number of
                halos.
            AssertionError: If the tree does not have all of the expected fields
                from the default LHaloTree format.
            AssertionError: If any of the halos have fields pointing to halos
                outside the tree (indicies exceeding nhalos).
            AssertionError: If there are any halos in a FOF group that are not
                in the same snapshot as the central.
            AssertionError: If the progenitors/descendants of any halo are not
                backwards/forwards in time.

        """
        # Check size
        nhalos = self.nhalos_per_tree[treenum]
        try:
            fields = list(tree.keys())
        except AttributeError:
            fields = list(tree.dtype.fields.keys())
        for k in fields:
            assert(len(tree[k]) == nhalos)
        # Check fields
        for k in self.raw_fields:
            assert(k in fields)
        # Check that halos are within tree
        for k in halo_fields:
            pos_flag = (tree[k] >= 0)
            assert((tree[k][pos_flag] < nhalos).all())
        # Check FOF central exists and all subs in one snapshot
        central = tree['FirstHaloInFOFgroup']
        assert((central >= 0).all())
        assert((tree['SnapNum'] == tree['SnapNum'][central]).all())
        # Check that progenitors/descendants are back/forward in time
        progen1 = tree['FirstProgenitor']
        progen2 = tree['NextProgenitor']
        descend = tree['Descendant'].astype('i4')
        has_descend = (descend >= 0)
        assert((tree['SnapNum'][descend[has_descend]] >
                tree['SnapNum'][has_descend]).all())
        # Check progenitors are back in time
        not_descend = np.logical_not(has_descend)
        descend[not_descend] = np.where(not_descend)[0]
        has_progen1 = (progen1 >= 0)
        has_progen2 = (progen2 >= 0)
        assert((tree['SnapNum'][progen1[has_progen1]] <=
                tree['SnapNum'][descend[has_progen1]]).all())
        assert((tree['SnapNum'][progen2[has_progen2]] <=
                tree['SnapNum'][descend[has_progen2]]).all())

    def validate_halo(self, halo):
        r"""Check that the halo conforms to expectations.

        Args:
            halo (np.ndarray): Single element structured array of information
                for a single halo.

        Raises:
            AssertionError: If the halo does not have length of 1.
            AssertionError: If the halo does not have all of the expected fields
                from the default LHaloTree format.

        """
        # Check size
        try:
            assert(len(halo[list(halo.keys())[0]]) == 1)
            fields = list(halo.keys())
        except AttributeError:
            assert(len(halo) == 1)
            fields = list(halo.dtype.fields.keys())
        # Check fields
        for k in self.raw_fields:
            assert(k in fields)

    def validate_fields(self, tree):
        r"""Check that the tree/halo has all of the expected fields.

        Args:
            tree (np.ndarray): Structured array of information for one or more
                halos.

        Raises:
            AssertionError: If the tree does not have all of the expected fields.

        """
        # Check fields
        try:
            fields = list(tree.keys())
        except AttributeError:
            fields = list(tree.dtype.fields.keys())
        for k in self.fields:
            assert(k in fields)
