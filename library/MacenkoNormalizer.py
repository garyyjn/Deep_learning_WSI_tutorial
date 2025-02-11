import numpy as np
import cupy as cp

# Based on code from: https://github.com/schaugf/HEnorm_python
class MacenkoNormalizer(object):
    """
    A stain normalization object
    """

    def __init__(self):
        # Default values
        self.HERef = np.array([[0.5626, 0.2159],
                               [0.7201, 0.8012],
                               [0.4062, 0.5581]])
        self.maxCRef = np.array([1.9705, 1.0308])

    @staticmethod
    def get_HE_maxC(img, Io=240, alpha=1, beta=0.15):
        # reshape image
        img = img.reshape((-1, 3))
        # calculate optical density
        OD = -np.log((img.astype(np.float) + 1) / Io)
        # remove transparent pixels
        ODhat = OD[~np.any(OD < beta, axis=1)]
        # compute eigenvectors
        eigvals, eigvecs = np.linalg.eigh(np.cov(ODhat.T))
        # project on the plane spanned by the eigenvectors corresponding to the two
        # largest eigenvalues
        That = ODhat.dot(eigvecs[:, 1:3])
        phi = np.arctan2(That[:, 1], That[:, 0])
        minPhi = np.percentile(phi, alpha)
        maxPhi = np.percentile(phi, 100 - alpha)

        vMin = eigvecs[:, 1:3].dot(np.array([(np.cos(minPhi), np.sin(minPhi))]).T)
        vMax = eigvecs[:, 1:3].dot(np.array([(np.cos(maxPhi), np.sin(maxPhi))]).T)
        # a heuristic to make the vector corresponding to hematoxylin first and the
        # one corresponding to eosin second
        if vMin[0] > vMax[0]:
            HE = np.array((vMin[:, 0], vMax[:, 0])).T
        else:
            HE = np.array((vMax[:, 0], vMin[:, 0])).T

        # rows correspond to channels (RGB), columns to OD values
        Y = np.reshape(OD, (-1, 3)).T
        # determine concentrations of the individual stains
        C = np.linalg.lstsq(HE, Y, rcond=None)[0]
        # normalize stain concentrations
        maxC = np.array([np.percentile(C[0, :], 99), np.percentile(C[1, :], 99)])

        return HE, maxC

    @staticmethod
    def standardize_brightness(img):
        p = np.percentile(img, 90)
        return np.clip(img * 255.0 / p, 0, 255).astype(np.uint8)

    def fit(self, reference_img, **kwargs):
        # reference_img = MacenkoNormalizer.standardize_brightness(reference_img)
        self.HERef, self.maxCRef = MacenkoNormalizer.get_HE_maxC(reference_img, **kwargs)

    def transform(self, img, get_H_E_results=False, Io=240, alpha=1, beta=0.15):
        """
        Normalize staining appearence of H&E stained images
        Input:
            I: RGB input image
            Io: (optional) transmitted light intensity

        Output:
            Inorm: normalized image
            Optional: (get_H_E_results)
                H: hematoxylin image
                E: eosin image

        Reference:
            A method for normalizing histology slides for quantitative analysis. M.
            Macenko et al., ISBI 2009
        """
        # img = MacenkoNormalizer.standardize_brightness(img)
        # define height and width of image
        h, w, c = img.shape
        # reshape image
        img = img.reshape((-1, 3))
        # calculate optical density
        OD = -np.log((img.astype(np.float) + 1) / Io)
        # remove transparent pixels
        ODhat = OD[~np.any(OD < beta, axis=1)]
        # compute eigenvectors
        eigvals, eigvecs = np.linalg.eigh(np.cov(ODhat.T))
        # project on the plane spanned by the eigenvectors corresponding to the two
        # largest eigenvalues
        That = ODhat.dot(eigvecs[:, 1:3])
        phi = np.arctan2(That[:, 1], That[:, 0])
        minPhi = np.percentile(phi, alpha)
        maxPhi = np.percentile(phi, 100 - alpha)

        vMin = eigvecs[:, 1:3].dot(np.array([(np.cos(minPhi), np.sin(minPhi))]).T)
        vMax = eigvecs[:, 1:3].dot(np.array([(np.cos(maxPhi), np.sin(maxPhi))]).T)
        # a heuristic to make the vector corresponding to hematoxylin first and the
        # one corresponding to eosin second
        if vMin[0] > vMax[0]:
            HE = np.array((vMin[:, 0], vMax[:, 0])).T
        else:
            HE = np.array((vMax[:, 0], vMin[:, 0])).T

        # rows correspond to channels (RGB), columns to OD values
        Y = np.reshape(OD, (-1, 3)).T
        # determine concentrations of the individual stains
        C = np.linalg.lstsq(HE, Y, rcond=None)[0]
        # normalize stain concentrations
        maxC = np.array([np.percentile(C[0, :], 99), np.percentile(C[1, :], 99)])
        tmp = np.divide(maxC, self.maxCRef)
        C2 = np.divide(C, tmp[:, np.newaxis])

        # recreate the image using reference mixing matrix
        Inorm = np.multiply(Io, np.exp(-self.HERef.dot(C2)))
        Inorm[Inorm > 255] = 254
        Inorm = np.reshape(Inorm.T, (h, w, 3)).astype(np.uint8)

        # unmix hematoxylin and eosin
        H = np.multiply(Io, np.exp(np.expand_dims(-self.HERef[:, 0], axis=1).dot(np.expand_dims(C2[0, :], axis=0))))
        H[H > 255] = 254
        H = np.reshape(H.T, (h, w, 3)).astype(np.uint8)

        E = np.multiply(Io, np.exp(np.expand_dims(-self.HERef[:, 1], axis=1).dot(np.expand_dims(C2[1, :], axis=0))))
        E[E > 255] = 254
        E = np.reshape(E.T, (h, w, 3)).astype(np.uint8)

        if get_H_E_results == True:
            return Inorm, H, E
        else:
            return Inorm



class MacenkoNormalizerCuda(object):
    """
    A stain normalization object
    """

    def __init__(self):
        # Default values
        self.HERef = cp.array([[0.5626, 0.2159],
                               [0.7201, 0.8012],
                               [0.4062, 0.5581]])
        self.maxCRef = cp.array([1.9705, 1.0308])

    @staticmethod
    def get_HE_maxC(img, Io=240, alpha=1, beta=0.15):
        # reshape image
        img = img.reshape((-1, 3))
        # calculate optical density
        OD = -cp.log((img.astype(cp.float) + 1) / Io)
        # remove transparent pixels
        ODhat = OD[~cp.any(OD < beta, axis=1)]
        # compute eigenvectors
        eigvals, eigvecs = cp.linalg.eigh(cp.cov(ODhat.T))
        # project on the plane spanned by the eigenvectors corresponding to the two
        # largest eigenvalues
        That = ODhat.dot(eigvecs[:, 1:3])
        phi = cp.arctan2(That[:, 1], That[:, 0])
        minPhi = cp.percentile(phi, alpha)
        maxPhi = cp.percentile(phi, 100 - alpha)

        vMin = eigvecs[:, 1:3].dot(cp.array([(cp.cos(minPhi), cp.sin(minPhi))]).T)
        vMax = eigvecs[:, 1:3].dot(cp.array([(cp.cos(maxPhi), cp.sin(maxPhi))]).T)
        # a heuristic to make the vector corresponding to hematoxylin first and the
        # one corresponding to eosin second
        if vMin[0] > vMax[0]:
            HE = cp.array((vMin[:, 0], vMax[:, 0])).T
        else:
            HE = cp.array((vMax[:, 0], vMin[:, 0])).T

        # rows correspond to channels (RGB), columns to OD values
        Y = cp.reshape(OD, (-1, 3)).T
        # determine concentrations of the individual stains
        C = cp.linalg.lstsq(HE, Y, rcond=None)[0]
        # normalize stain concentrations
        maxC = cp.array([cp.percentile(C[0, :], 99), cp.percentile(C[1, :], 99)])

        return HE, maxC

    @staticmethod
    def standardize_brightness(img):
        p = cp.percentile(img, 90)
        return cp.clip(img * 255.0 / p, 0, 255).astype(cp.uint8)

    def fit(self, reference_img, **kwargs):
        # reference_img = MacenkoNormalizer.standardize_brightness(reference_img)
        self.HERef, self.maxCRef = MacenkoNormalizer.get_HE_maxC(reference_img, **kwargs)
        self.HERef = cp.asarray(self.HERef)
        self.maxCRef = cp.asarray(self.maxCRef)

    def transform(self, img, get_H_E_results=False, Io=240, alpha=1, beta=0.15):
        """
        Normalize staining appearence of H&E stained images
        Input:
            I: RGB input image
            Io: (optional) transmitted light intensity

        Output:
            Inorm: normalized image
            Optional: (get_H_E_results)
                H: hematoxylin image
                E: eosin image

        Reference:
            A method for normalizing histology slides for quantitative analysis. M.
            Macenko et al., ISBI 2009
        """
        img = cp.asarray(img)
        # img = MacenkoNormalizer.standardize_brightness(img)
        # define height and width of image
        h, w, c = img.shape
        # reshape image
        img = img.reshape((-1, 3))
        # calculate optical density
        OD = -cp.log((img.astype(float) + 1) / Io)
        # remove transparent pixels
        ODhat = OD[~cp.any(OD < beta, axis=1)]
        # compute eigenvectors
        eigvals, eigvecs = cp.linalg.eigh(cp.cov(ODhat.T))
        # project on the plane spanned by the eigenvectors corresponding to the two
        # largest eigenvalues
        That = ODhat.dot(eigvecs[:, 1:3])
        phi = cp.arctan2(That[:, 1], That[:, 0])
        #print(phi)
        minPhi = cp.percentile(phi, alpha)
        maxPhi = cp.percentile(phi, 100 - alpha)
        #minphi = cp.asarray(minphi)
        #print(minPhi)
        #print(cp.cos(minPhi))
        #print(cp.sin(minPhi))
        #print(cp.array([(cp.cos(minPhi), cp.sin(minPhi))]).T)
        vMin = eigvecs[:, 1:3].dot(cp.array([(cp.cos(minPhi), cp.sin(minPhi))]).T)
        vMax = eigvecs[:, 1:3].dot(cp.array([(cp.cos(maxPhi), cp.sin(maxPhi))]).T)
        # a heuristic to make the vector corresponding to hematoxylin first and the
        # one corresponding to eosin second
        if vMin[0] > vMax[0]:
            HE = cp.array((vMin[:, 0], vMax[:, 0])).T
        else:
            HE = cp.array((vMax[:, 0], vMin[:, 0])).T

        # rows correspond to channels (RGB), columns to OD values
        Y = cp.reshape(OD, (-1, 3)).T
        # determine concentrations of the individual stains
        C = cp.linalg.lstsq(HE, Y, rcond=None)[0]
        # normalize stain concentrations
        maxC = cp.array([cp.percentile(C[0, :], 99), cp.percentile(C[1, :], 99)])
        tmp = cp.divide(maxC, self.maxCRef)
        C2 = cp.divide(C, tmp[:, cp.newaxis])

        # recreate the image using reference mixing matrix
        Inorm = cp.multiply(Io, cp.exp(-self.HERef.dot(C2)))
        Inorm[Inorm > 255] = 254
        Inorm = cp.reshape(Inorm.T, (h, w, 3)).astype(cp.uint8)

        # unmix hematoxylin and eosin
        H = cp.multiply(Io, cp.exp(cp.expand_dims(-self.HERef[:, 0], axis=1).dot(cp.expand_dims(C2[0, :], axis=0))))
        H[H > 255] = 254
        H = cp.reshape(H.T, (h, w, 3)).astype(cp.uint8)

        E = cp.multiply(Io, cp.exp(cp.expand_dims(-self.HERef[:, 1], axis=1).dot(cp.expand_dims(C2[1, :], axis=0))))
        E[E > 255] = 254
        E = cp.reshape(E.T, (h, w, 3)).astype(cp.uint8)


        Inorm = cp.asnumpy(Inorm)
        H = cp.asnumpy(Inorm)
        E = cp.asnumpy(E)
        if get_H_E_results == True:
            return Inorm, H, E
        else:
            return Inorm
