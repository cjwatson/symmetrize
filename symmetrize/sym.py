#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
@author: R. Patrick Xian
"""

# ============================================= #
#  Symmetrizing deformation and its estimation  #
# ============================================= #

from __future__ import print_function, division
from . import pointops as po
import numpy as np
from numpy.linalg import norm
import scipy.optimize as opt
import scipy.ndimage as ndi
import skimage.transform as skit
import cv2


def pointsetTransform(points, hgmat):
    """
    Apply transform to the positions of a point set.

    :Parameters:
        points : 2D array
            Cartesian pixel coordinates of the points.
        hgmat : 2D array
            Transformation matrix (homography).

    :Return:
        points_transformed : 2D array
            Transformed Cartesian pixel coordinates.
    """

    points_reformatted = po.cart2homo(points)
    points_transformed = po.homo2cart(cv2.transform(points_reformatted, hgmat))

    return points_transformed


def rotVertexGenerator(center, fixedvertex=None, cvd=None, arot=None, nside=None, direction=-1,
                    scale=1, diagdir=None, ret='all', rettype='float32'):
    """
    Generation of the vertices of symmetric polygons.

    :Parameters:
        center : (int, int)
            Pixel positions of the symmetry center (row pixel, column pixel).
        fixedvertex : (int, int) | None
            Pixel position of the fixed vertex (row pixel, column pixel).
        cvd : numeric | None
            Center-vertex distance.
        arot : float | None
            Spacing in angle of rotation.
        nside : int | None
            The total number of sides for the polygon (to be implemented).
        direction : int | -1
            Direction of angular rotation (1 = counterclockwise, -1 = clockwise)
        scale : float | 1
            Radial scaling factor.
        diagdir : str | None
            Diagonal direction of the polygon ('x' or 'y').
        ret : str | 'all'
            Return type. Specify 'all' returns all vertices, specify 'generated'
            returns only the generated ones (without the fixedvertex in the argument).

    :Return:
        vertices : 2D array
            Collection of generated vertices.
    """

    try:
        cvd = abs(cvd)
    except:
        pass

    try:
        center = tuple(center)
    except:
        raise TypeError('The center coordinates should be provided in a tuple!')

    if type(arot) in (int, float):
        nangles = int(np.round(360 / abs(arot))) - 1 # Number of angles needed
        rotangles = direction*np.linspace(1, nangles, nangles)*arot
    else:
        nangles = len(arot)
        rotangles = np.cumsum(arot)

    # Generating polygon vertices starting with center-vertex distance
    if fixedvertex is None:
        if diagdir == 'x':
            fixedvertex = [center[0], cvd + center[1]]
        elif diagdir == 'y':
            fixedvertex = [cvd + center[0], center[1]]

    # Reformat the input array to satisfy function requirement
    fixedvertex_reformatted = np.array(fixedvertex, dtype='float32', ndmin=2)[None,...]

    if ret == 'all':
        vertices = [fixedvertex]
    elif ret == 'generated':
        vertices = []

    if type(scale) in (int, float):
        scale = np.ones((nangles,)) * scale

    # Generate reference points by rotation and scaling
    for ira, ra in enumerate(rotangles):

        rmat = cv2.getRotationMatrix2D(center, ra, scale[ira])
        rotvertex = np.squeeze(cv2.transform(fixedvertex_reformatted, rmat)).tolist()
        vertices.append(rotvertex)

    return np.asarray(vertices, dtype=rettype)


def _symcentcost(pts, center, mean_center_dist, mean_edge_dist, rotsym=6, weights=(1, 1, 1)):
    """
    Symmetrization-centralization loss function.

    :Parameters:
        pts : list/tuple
            Pixel coordinates of the points (representing polygon vertices).
        center : list/tuple
            Pixel coordinates of the center.
        mean_center_dist : float
            Mean center-vertex distance.
        mean_edge_dist : float
            Mean nearest-neighbor vertex-vertex distance.
        rotsym : int
            Order of rotational symmetry.
        weights : list/tuple/array
            Weights to apply to the terms (centeredness, center-vertex symmetry, vertex-vertex symmetry).

    :Return:
        sc_cost : float
            The overall cost function.
    """

    halfsym = rotsym // 2

    # Calculate the deviation from center
    if np.allclose(weights[0], 0.):
        f_centeredness = 0
    else:
        # Extract the point pair
        pts1 = pts[range(0, halfsym), :]
        pts2 = pts[range(halfsym, rotsym), :]
        centralcoords = (pts1 + pts2) / 2
        centerdev = centralcoords - center
        # wcent = 1 / np.var(centerdev)
        f_centeredness = weights[0] * np.sum(centerdev**2) / halfsym

    # Calculate the distance-to-center difference between all symmetry points
    if np.allclose(weights[1], 0.):
        f_cvdist = 0
    else:
        centerdist = po.cvdist(pts, center)
        cvdev = centerdist - mean_center_dist
        # wcv = 1 / np.var(cvdev)
        f_cvdist = weights[1] * np.sum(cvdev**2) / rotsym

    # Calculate the edge difference between all neighboring symmetry points
    if np.allclose(weights[2], 0.):
        f_vvdist = 0
    else:
        edgedist = po.vvdist(pts, 1)
        vvdev = edgedist - mean_edge_dist
        # wvv = 1 / np.var(vvdev)
        f_vvdist = weights[2] * np.sum(vvdev**2) / rotsym

    # Calculate the overall cost function
    fsymcent = np.array([f_centeredness, f_cvdist, f_vvdist])
    sc_cost = np.sum(fsymcent)

    return sc_cost


def _refset(coeffs, landmarks, center, direction=1, include_center=False):
    """
    Calculate the reference point set.

    :Parameters:
        coeffs : 1D array
            Vertex generator coefficients for fitting.
        landmarks : 2D array
            Landmark positions extracted from distorted image.
        center : list/tuple
            Pixel position of the image center.
        direction : int | 1
            Circular direction to generate the vertices.

    :Returns:
        lmkwarped : 2D array
            Exactly transformed landmark positions (acting as reference positions).
        H : 2D array
            Estimated homography.
    """

    arots, scales = coeffs.reshape((2, coeffs.size // 2))

    # Generate reference point set
    refs = rotVertexGenerator(center, fixedvertex=landmarks[0,:], arot=arots,
                           direction=direction, scale=scales, ret='generated')

    # Include the center if it needs to be included
    if include_center:
        landmarks = np.concatenate((landmarks, np.asarray(center)[None,:]), axis=0)
        refs = np.concatenate((refs, np.asarray(center)[None,:]), axis=0)

    # Determine the homography that bridges the landmark and reference point sets
    H, _ = cv2.findHomography(landmarks, refs)
    # Calculate the actual point set transformed by the homography
    # ([:,:2] is used to transform into Cartesian coordinate)
    lmkwarped = np.squeeze(cv2.transform(landmarks[None,...], H))[:,:2]

    return lmkwarped, H


def _refsetcost(coeffs, landmarks, center, mcd, med, direction=-1, rotsym=6,
                weights=(1, 1, 1), include_center=False):
    """
    Reference point set generator cost function.

    :Parameters:
        coeffs : 1D array
            Point set generator coefficients (angle of rotation and scaling factors).
        landmarks : list/tuple
            Pixel coordinates of the landmarks.
        center : list/tuple
            Pixel coordinates of the Gamma point.
        direction : str | -1
            Direction to generate the point set, -1 (cw) or 1 (ccw).
        rotsym : int | 6
            Order of rotational symmetry
        weights : tuple/list
        include_center : bool | False
            Option to include the center of pattern.

    :Return:
        rs_cost : float
            Scalar value of the reference set cost function.
    """

    landmarks_warped, _ = _refset(coeffs, landmarks, center, direction=direction, include_center=include_center)
    rs_cost = _symcentcost(landmarks_warped, center, mcd, med, rotsym, weights=weights)

    return rs_cost


def refsetopt(init, refpts, center, mcd, med, direction=-1, rotsym=6, weights=(1, 1, 1),
                optfunc='minimize', optmethod='Nelder-Mead', include_center=False, **kwds):
    """ Optimization to find the optimal reference point set.

    :Parameters:
        init : list/tuple
            Initial conditions.
        refpts : 2D array
            Reference points.
        center : list/tuple/array
            Image center position.
        mcd : numeric
            Mean center-vertex distance.
        med : numeric
            Mean edge distance.
        niter : int | 200
            Number of iterations.
        direction : int | -1
            Direction of the target generator.
        rotsym : int | 6
            Order of rotational symmetry.
        weights : tuple/list/array | (1, 1, 1)
            Weights assigned to the objective function.
        optfunc : str/function | 'minimize'
            Optimizer function.
            :'basinhopping': use the `scipy.optimize.basinhopping()` function.
            :'minimize': use the `scipy.optimize.minimize()` function.
            :others: use other user-specified optimization function `optfunc`.
        optmethod : string | 'Nelder-Mead'
            Name of the optimization method.
        include_center : bool | False
            Option to include center.
        **kwds : keyword arguments
            Keyword arguments passed to the specified optimizer function.
    """

    if optfunc == 'basinhopping':
        niter = int(kwds.pop('niter', 50))
        res = opt.basinhopping(_refsetcost, init, niter=niter, minimizer_kwargs={'method':optmethod,
        'args':(refpts, center, mcd, med, direction, rotsym, weights, include_center)}, **kwds)

    elif optfunc == 'minimize':
        image = kwds.pop('image', None)
        res = opt.minimize(_refsetcost, init, args=(refpts, center, mcd, med, direction, rotsym,
                        weights, include_center), method=optmethod, **kwds)

    else: # Use other optimization function
        res = optfunc(_refsetcost, init, args, **kwds)

    # Calculate the optimal warped point set and the corresponding homography
    ptsw, H = _refset(res['x'], refpts, center, direction, include_center)

    return ptsw, H


# ====================================== #
#  Deformation fields and their algebra  #
# ====================================== #

def imgWarping(img, hgmat=None, landmarks=None, refs=None, rotangle=None, **kwds):
    """
    Perform image warping based on a generic affine transform (homography).

    :Parameters:
        img : 2D array
            Input image (distorted).
        hgmat : 2D array
            Homography matrix.
        landmarks : list/array
            Pixel coordinates of landmarks (distorted).
        refs : list/array
            Pixel coordinates of reference points (undistorted).
        rotangle : float
            Rotation angle (in degrees).
        **kwds : keyword argument

    :Returns:
        imgaw : 2D array
            Image after affine warping.
        hgmat : 2D array
            (Composite) Homography matrix for the tranform.
    """

    # Calculate the homography matrix, if not given
    if hgmat is None:

        landmarks = np.asarray(landmarks, dtype='float32')
        refs = np.asarray(refs, dtype='float32')
        hgmat, _ = cv2.findHomography(landmarks, refs)

    # Add rotation to the transformation, if specified
    if rotangle is not None:

        center = kwds.pop('center', ndi.measurements.center_of_mass(img))
        center = tuple(center)
        rotmat = cv2.getRotationMatrix2D(center, angle=rotangle, scale=1)
        # Construct rotation matrix in homogeneous coordinate
        rotmat = np.concatenate((rotmat, np.array([0, 0, 1], ndmin=2)), axis=0)
        # Construct composite operation
        hgmat = np.dot(rotmat, hgmat)

    imshape = kwds.pop('outshape', img.shape)

    # Perform composite image transformation
    imgaw = cv2.warpPerspective(img, hgmat, imshape, **kwds)

    return imgaw, hgmat


def applyWarping(imgstack, axis, hgmat):
    """
    Apply warping transform to a stack of images along the specified axis.

    :Parameters:
        imgstack : 3D array
            Image stack before warping correction.
        axis : int
            Axis to iterate over to apply the transform.
        hgmat : 2D array
            Homography matrix.

    :Return:
        imstack_transformed : 3D array
            Stack of images after correction for warping.
    """

    imgstack = np.moveaxis(imgstack, axis, 0)
    imgstack_transformed = np.zeros_like(imgstack)
    nimg = imgstack.shape[0]

    for i in range(nimg):
        img = imgstack[i,...]
        imgstack_transformed[i,...] = cv2.warpPerspective(img, hgmat, img.shape)

    imgstack_transformed = np.moveaxis(imgstack_transformed, 0, axis)

    return imgstack_transformed


def coordinate_matrix_2D(image, coordtype='homogeneous', stackaxis=0):
    """ Generate pixel coordinate matrix for a 2D image.

    :Parameters:
        image : 2D array
            2D image matrix.
        coordtype : str | 'homogeneous'
            Type of generated coordinates ('homogeneous' or 'cartesian').
        stackaxis : int | 0
            The stacking axis for the coordinate matrix, e.g. a stackaxis
            of 0 means that the coordinates are stacked along the first dimension.

    :Return:
        coordmat : 3D array
            Coordinate matrix stacked along the specified axis.
    """

    nr, nc = image.shape
    rgrid, cgrid = np.meshgrid(range(0, nc), range(0, nr))

    if coordtype == 'cartesian':
        coordmat = np.stack((cgrid, rgrid), axis=stackaxis)

    elif coordtype == 'homogeneous':
        zgrid = np.ones((nr, nc))
        coordmat = np.stack((cgrid, rgrid, zgrid), axis=stackaxis)

    return coordmat


def deform_field_merge(operation, *fields):
    """ Combine multiple deformation fields.
    """

    return np.asarray(reduce(operation, fields))


# =============================== #
#  Image pattern pose estimation  #
# =============================== #

def foldcost(image, center, axis=1):
    """
    Cost function for folding over an image along an image axis crossing the image center.

    :Parameters:
        image : 2d array
            Image to fold over.
        center : tuple/list
            Pixel coordinates of the image center (row, column).
        axis : int | 1
            Axis along which to fold over the image (1 = column-wise, 0 = row-wise).
    """

    r, c = image.shape
    rcent, ccent = center

    if axis == 1: # Column-symmetric pose

        iccent = c-ccent
        cmin = min(ccent, iccent) # Minimum distance towards the image center

        if cmin == ccent: # Flip the column index range 0:ccent
            flipped = image[:, :ccent][:, ::-1]
            cropped = image[:, ccent:2*cmin]
        else: # Flip the column index range ccent-iccent:ccent
            flipped = image[:, ccent-iccent:ccent][:, ::-1]
            cropped = image[:, ccent:]

    elif axis == 0: # Row-symmetric pose

        irrcent = r-rcent
        rmin = min(rcent, irrcent)

        if rmin == rcent:
            flipped = image[:rcent, :][::-1, :]
            cropped = image[rcent:2*rmin, :]
        else:
            flipped = image[rcent-irrcent:rcent, :][::-1, :]
            cropped = image[rcent:, :]

    diff = flipped - cropped

    return norm(diff)


def sym_pose_estimate(image, center, axis=1, angle_range=None, angle_start=-90,
                        angle_stop=90, angle_step=0.1):
    """
    Estimate the best presenting angle using rotation-mirroring grid search such that
    the image is symmetric about an image axis (row or column). The algorithm calculates
    the intensity difference mirrored from the center of the image at a range of rotation
    angles and pick the angle that minimizes this difference.

    :Parameters:
        image : 2d array
            Input image for optimal presenting angle estimation.
        center : tuple/list
            The pixel coordinates of the image center.
        axis : int | 1
            The axis of reflection (0 = row, 1 = column).
        angle_range : list/array | None
            The range of angles to be tested.
        angle_start, angle_stop, angle_step : float, float, float | -90, 90, 0.1
            The bounds and step to generate.

    :Returns:
        aopt : float
            The optimal rotation needed for posing image symmetric about an image axis.
        imrot : 2d array
            Image rotated to the optimal presenting angle.
    """

    if angle_range is not None:
        agrange = angle_range
    else:
        agrange = np.arange(angle_start, angle_stop, angle_step)

    nangles = len(agrange)
    fval = np.zeros((2, nangles))
    for ia, a in enumerate(agrange):

        imr = skit.rotate(image, angle=a, center=center, resize=False)

        # Fold image along one axis
        fval[0, ia] = a
        fval[1, ia] = foldcost(imr, center=center, axis=axis)

    aopt = fval[0, np.argmin(fval[1,:])]
    imrot = skit.rotate(image, angle=aopt, center=center, resize=False)

    return aopt, imrot
