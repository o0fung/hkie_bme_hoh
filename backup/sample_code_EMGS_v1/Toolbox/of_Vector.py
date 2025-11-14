import numpy
import sys


def Rx(theta):
    # Rotation Matrix in X-Axis
    return numpy.matrix([[ 1, 0           , 0           ],
                         [ 0, numpy.cos(theta),-numpy.sin(theta)],
                         [ 0, numpy.sin(theta), numpy.cos(theta)]])
  
def Ry(theta):
    # Rotation Matrix in Y-Axis
    return numpy.matrix([[ numpy.cos(theta), 0, numpy.sin(theta)],
                         [ 0           , 1, 0           ],
                         [-numpy.sin(theta), 0, numpy.cos(theta)]])
  
def Rz(theta):
    # Rotation Matrix in Z-Axis
    return numpy.matrix([[ numpy.cos(theta), -numpy.sin(theta), 0 ],
                         [ numpy.sin(theta), numpy.cos(theta) , 0 ],
                         [ 0           , 0            , 1 ]])
    
def EulerXYZ(phi, theta, psi):
    # General XYZ Elementary Rotation Sequence 
    # Using Matrix Multiplication
    # Get Rotation Matrix from Euler Angles
    Rxyz = Rz(psi) * Ry(theta) * Rx(phi)
    return Rxyz

def EulerZYZ(phi, theta, psi):
    # General ZYZ Elementary Rotation Sequence 
    # Using Matrix Multiplication
    # Get Rotation Matrix from Euler Angles
    Rzyz = Rz(psi) * Ry(theta) * Rz(phi)
    return Rzyz

def inv_EulerXYZ(R):
    # Reverse XYZ Elementary Rotation
    # Get Euler Angles from Rotation Matrix
    # Get Phi (X), Theta (Y), Psi (Z), respectively
    tol = sys.float_info.epsilon * 10
    if abs(R.item(0,0)) < tol and abs(R.item(1,0)) < tol:
        eul1 = 0
        eul2 = numpy.atan2(-R.item(2,0), R.item(0,0))
        eul3 = numpy.atan2(-R.item(1,2), R.item(1,1))
    else:   
        eul1 = numpy.atan2(R.item(1,0), R.item(0,0))
        sp = numpy.sin(eul1)
        cp = numpy.cos(eul1)
        eul2 = numpy.atan2(-R.item(2,0), cp * R.item(0,0) + sp * R.item(1,0))
        eul3 = numpy.atan2(sp * R.item(0,2) - cp * R.item(1,2), cp * R.item(1,1) - sp * R.item(0,1))
        
    return eul1, eul2, eul3

def inv_EulerZYZ(R):
    # Reverse ZYZ Elementary Rotation
    # Get Euler Angles from Rotation Matrix
    # Get Phi (Z), Theta (Y), Psi (Z), respectively
    eul1 = numpy.atan2(R.item(1,2), R.item(0,2))
    sp = numpy.sin(eul1)
    cp = numpy.cos(eul1)
    eul2 = numpy.atan2(cp * R.item(0,2) + sp * R.item(1,2), R.item(2,2))
    eul3 = numpy.atan2(-sp * R.item(0,0) + cp * R.item(1,0), -sp * R.item(0,1) + cp * R.item(1,1))

    return eul1, eul2, eul3

def rotate(R, v):
    return numpy.dot(R, v)

def rotation_matrix_from_vectors(vec1, vec2):
    """ Find the rotation matrix that aligns vec1 to vec2
    :param vec1: A 3d "source" vector
    :param vec2: A 3d "destination" vector
    :return mat: A transform matrix (3x3) which when applied to vec1, aligns it with vec2.
    """
    a, b = (vec1 / numpy.linalg.norm(vec1)).reshape(3), (vec2 / numpy.linalg.norm(vec2)).reshape(3)
    v = numpy.cross(a, b)
    c = numpy.dot(a, b)
    s = numpy.linalg.norm(v)
    kmat = numpy.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    R = numpy.eye(3) + kmat + numpy.dot(kmat, kmat) * ((1 - c) / (s ** 2))
    
    return R
