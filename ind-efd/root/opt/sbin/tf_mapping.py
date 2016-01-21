#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################


'''
This module will perform the Time/Frequency mapping over input data.
'''

import numpy as np
import math
from collections import namedtuple

DEBUG = False
#DEBUG = True

try:
    ## Use long double precision floating point (np.float128, 'f16')
    #DTYPE = '<f16'
    DTYPE = np.float128
except AttributeError:
    ## 32-bit processors/python only supports double precision floating point (np.float64, 'f8')
    #DTYPE = '<f8'
    DTYPE = np.float64
    #raise

## Create TF_Map namedtuple class.
TF_Map = namedtuple('TF_Map', ['t0', 'T', 'T2', 'F', 'F2'])

#Null_TF_Map = TF_Map(t0=None, T=None, T2=None, F=None, F2=None)
Null_TF_Map = TF_Map(t0=0, T=0, T2=0, F=0, F2=0)


##############################################################################

def tf_map_calculate(tdata, ydata, sample_freq, fft_length=0):

    if DEBUG:
        print("DEBUG: tf_map_calculate: sample_freq = {}".format(sample_freq))
        print("DEBUG: tf_map_calculate: fft_length = {}".format(fft_length))
        print("DEBUG: tf_map_calculate: tdata = {}".format(tdata))
        print("DEBUG: tf_map_calculate: ydata = {}".format(ydata))

    ##
    ## Calculate Effective Time-Length and Effective Bandwidth around max peak.
    ##
    
    num = len(tdata)
    mid = num // 2

    if not fft_length:
        fft_length = num
    
    ##
    ## Calculate t0
    ##
    ##       sum( t * s^2 )
    ## T^2 = --------------
    ##       sum( s^2 )
    ##

    s = ydata
    
    ## square the sample data.
    s2 = s * s
    
    ## sum up all s2 values.
    sum_s2 = s2.sum()
    sum_s2 = np.sum(s2)

    ## generate linear time array (t) based at zero.
    t = tdata - tdata[0]
    
    t_s2 = t * s2
    
    sum_t_s2 = t_s2.sum()
    
    t0 = sum_t_s2 / sum_s2
    if not math.isfinite(t0):
        t0 = 0.0

    ##
    ## Calculate T^2 -- "equivalent time-length"
    ##
    ##       sum( ((t - t0)^2) * s^2 )
    ## T^2 = -------------------------
    ##       sum( s^2 )
    ##
    
    t_t0_delta = t - t0
    
    t_t0_delta2 = t_t0_delta * t_t0_delta
    
    t_t0_delta2_s2 = t_t0_delta2 * s2
    
    sum_t_t0_delta2_s2 = t_t0_delta2_s2.sum()
    
    T2 = sum_t_t0_delta2_s2 / sum_s2
    if not math.isfinite(T2):
        T2 = 0.0
    
    T = math.sqrt(T2)
    
    ##
    ## Calculate W^2 -- "equivalent bandwidth"
    ##
    ##       sum( f^2 * mag(xf)^2 ) 
    ## W^2 = ----------------------
    ##       sum( mag(xf)^2 )
    ##
    ##
    ## ----------------------------------
    ## Matlab sample.
    ## ----------------------------------
    ##
    ## %FFT (checked by Alan and Liang)
    ## sampling_freq = 1e9
    ## N = 65536
    ## P = abs(fft(volt1,N));
    ## %P = fftshift(P);
    ## F = (0:N-1)*sampling_freq/N;
    ## F = F';
    ## 
    ## %plot(F(1:(N/2)),P(1:(N/2))),
    ## %xlabel('frequency /Hz');
    ## 
    ## % Calculate W^2
    ## 
    ## for m=1:(N/2)
    ##     B1(m) = F(m)*F(m)*P(m)*P(m);
    ## end
    ## B1 = B1';
    ## B = sum(B1)
    ## 
    ## for n=1:(N/2)
    ##     C1(n) = P(n)*P(n);
    ## end
    ## 
    ## C1 = C1';
    ## C = sum(C1)
    ## 
    ## W_square = B/C
    ## 
    ## W = (W_square) ^ (0.5)
    ## 
    

    ## Perform FFT.
    ## FIXME: my concern here is the fft will be truncated for fft_length < data length.
    ## FIXME: therefore only the first fft_length values will be used, most likely missing,
    ## FIXME: the peak, which is the region of interest.
    ## FIXME: this shouldn't be a problem on the EFD system if fft_length == data_length,
    ## FIXME: which is what we are proposing to do.
    x1 = np.fft.rfft(ydata, n=fft_length)

    ## Remove 1st element (zero frequency component)
    x2 = x1[:-1]
    ## Remove last element (retaining zero frequency component) -- WHY ???
    #x2 = x1[1:]

    ## rfft returns array of dtype=float64.
    ## Changing to float128 gives slightly different answer to Alan's sample code.
    ## float128 is probably more accurate but I've left it as float64 to match the sample code.
    ## NOTE: float128 is only availalbe on 64-bit python versions.
    #x2 = x2[:-1].astype(DTYPE)

    x3 = abs(x2)

    f1 = np.fft.rfftfreq(n=fft_length, d=1.0/sample_freq)

    ## Remove 1st element (zero frequency component)
    #f1 = f1[1:]
    ## Remove last element (retaining zero frequency component) -- WHY ???
    f1 = f1[:-1]

    f2 = f1 * f1
    
    y2 = x3 * x3
    
    y2_f2 = y2 * f2

    d = y2_f2.sum()
    e = y2.sum()

    W2 = d / e
    if not math.isfinite(W2):
        W2 = 0.0

    W = math.sqrt(W2)
    
    tf_map = TF_Map(t0=t0, T=T, T2=T2, F=W, F2=W2)

    if DEBUG:
        print("DEBUG: Calculate Effective Time-Length and Effective Bandwidth ...")
        print
        print("DEBUG: tdata = {}".format(tdata.__array_interface__))
        print("tdata = {} ... {} ... {}".format(tdata[:3], tdata[mid-1:mid+1+1], tdata[-3:]))
        print("DEBUG: ydata = {}".format(ydata.__array_interface__))
        print("ydata = {} ... {} ... {}".format(ydata[:3], ydata[mid-1:mid+1+1], ydata[-3:]))
        print
        print("DEBUG: num = {}".format(num))
        print("DEBUG: mid = {}".format(mid))
        print("DEBUG: fft_length = {}".format(fft_length))
        print
        print("DEBUG: s = {}".format(s.__array_interface__))
        print("s = {} ... {} ... {}".format(s[:3], s[mid-1:mid+1+1], s[-3:]))
        print("DEBUG: s2 = {}".format(s.__array_interface__))
        print("s2 = {} ... {} ... {}".format(s2[:3], s2[mid-1:mid+1+1], s2[-3:]))
        print("DEBUG: sum_s2 = {}".format(sum_s2))
        print("DEBUG: sum_s2 = {}".format(sum_s2))
        print
        print("DEBUG: t = {} ... {} ... {}".format(t[:3], t[mid-1:mid+1+1], t[-3:]))
        print("DEBUG: t_s2 = {} ... {} ... {}".format(t_s2[:3], t_s2[mid-1:mid+1+1], t_s2[-3:]))
        print("DEBUG: sum_t_s2 = {}".format(sum_t_s2))
        print("DEBUG: t0 = {}".format(t0))
        print
        print("DEBUG: t_t0_delta = {} ... {} ... {}".format(t_t0_delta[:3], t_t0_delta[mid-1:mid+1+1], t_t0_delta[-3:]))
        print("DEBUG: t_t0_delta2 = {} ... {} ... {}".format(t_t0_delta2[:3], t_t0_delta2[mid-1:mid+1+1], t_t0_delta2[-3:]))
        print("DEBUG: t_t0_delta2_s2 = {} ... {} ... {}".format(t_t0_delta2_s2[:3], t_t0_delta2_s2[mid-1:mid+1+1], t_t0_delta2_s2[-3:]))
        print("DEBUG: sum_t_t0_delta2_s2 = {}".format(sum_t_t0_delta2_s2))
        print("DEBUG: T2 = {}".format(T2))
        print("DEBUG: T = {}".format(T))
        print
        print('DEBUG: Calculate W^2 -- "equivalent bandwidth"')
        print
        print("DEBUG: tdata = {}".format(tdata.__array_interface__))
        print("tdata = {} ... {} ... {}".format(tdata[:3], tdata[mid-1:mid+1+1], tdata[-3:]))
        print("DEBUG: ydata = {}".format(ydata.__array_interface__))
        print("ydata = {} ... {} ... {}".format(ydata[:3], ydata[mid-1:mid+1+1], ydata[-3:]))
        print
        print("DEBUG: x1 = {}".format(x1.__array_interface__))
        print("DEBUG: x1 = {} ... {} ... {}".format(x1[:3], x1[mid-1:mid+1+1], x1[-3:]))
        print("DEBUG: x1[-1] = {}".format(x1[-1]))
        print
        print("DEBUG: f1 = {} ... {} ... {}".format(f1[:3], f1[mid-1:mid+1+1], f1[-3:]))
        print("DEBUG: f2 = {} ... {} ... {}".format(f2[:3], f2[mid-1:mid+1+1], f2[-3:]))
        print
        print("DEBUG: y2 = {} ... {} ... {}".format(y2[:3], y2[mid-1:mid+1+1], y2[-3:]))
        print("DEBUG: y2_f2 = {} ... {} ... {}".format(y2_f2[:3], y2_f2[mid-1:mid+1+1], y2_f2[-3:]))
        print("DEBUG: d = {}".format(d))
        print("DEBUG: e = {}".format(e))
        print
        print("DEBUG: W2 = {}".format(W2))
        print("DEBUG: W = {}".format(W))
        print
        print("DEBUG: tf_map = {}".format(tf_map))
        print

    return tf_map
    
##############################################################################

def get_sample_data(sim=False):
    """Get sample data from buffer (or generate simulated sample data)."""
    
    freq = 50.0
    
    duration = 0.040
    
    #num = 16
    num = 10*1000*1000
    
    #max = 0x7FFF
    #max = (1 << 16) - 1
    max = (1 << 15) - 1
    
    if 0:
        min_max = (0, max)
        dtype = '<u2'
    else:
        min_max = (-max, max)
        dtype = '<i2'
    
    sig = signal_generate(freq=freq, duration=duration, num=num, min_max=min_max, endpoint=True, dtype=dtype)
    
    #print("sig =",sig)
    #print
    
    return sig
    
def main():
    """Main entry if running this module directly."""
    
    import sys
    import os.path
    import mmap
    import peak_detect

    import sample_data
    from generate_sinusoid import signal_generate

    ## FIXME: set this to true to use same fixed assumptions as IND matlab script.     
    #FIXME_IND_MATLAB_HACK = False    
    FIXME_IND_MATLAB_HACK = True    

    ## Set True => raw A2D data (16-bit signed).
    INPUT_DATA_IS_RAW_A2D = False    
    #INPUT_DATA_IS_RAW_A2D = True    

    ## Set True => converted floating point values.
    #INPUT_DATA_IS_FLOAT = False    
    INPUT_DATA_IS_FLOAT = True    

    print("Python System Version = {}".format(sys.version))
    print
    
#    data = get_sample_data(sim=True)
#    print("sample_data =", data)
#    print
#    print("sample_data.format =".rjust(20), sample_data.format)
#    print("sample_data.data =".rjust(20), sample_data.data)
    
    if INPUT_DATA_IS_RAW_A2D:
        ## /dev/mem
#        fdev = os.path.join(os.sep, "dev","mem")
#        length = 2 * 1000 * 1000
#        length = 10 * 1000 * 1000
    
        #sample_freq = 250 * 1000 * 1000
        
        ##
        ## files with binary data.
        ##

        fname = 'scope_0.bin'
        sample_freq = 1 * 1000 * 1000 * 1000
    
        #fname = 'scope_5.bin'
        #sample_freq = 1 * 1000 * 1000 * 1000
        
        ##
        ## FIXME: force sample freq to 500MS/s => Ts=2ns, to match matlab script.
        ##
        if FIXME_IND_MATLAB_HACK:
            #print("DEBUG: FORCE: Fs=500MS/s, Ts=2ns.")
            #sample_freq = 500 * 1000 * 1000
            print("DEBUG: FORCE: Fs=1GS/s, Ts=1ns.")
            sample_freq = 1 * 1000 * 1000 * 1000
            sample_period = 1.0 / sample_freq
        
        fdir = os.path.join('..', 'Data')
        fpath = os.path.join(fdir,fname)
        print("DEBUG: mmap: {}".format(fpath))
        stage1_xdata, stage1_ydata = get_mmap_sample_data(fpath)

        xfactor = 1 / sample_freq
        #vpp = 2.5
        #vpp = 2.0
        vpp = 1.0
        bits = 16
        ylevels = (1 << bits)
        yfactor = vpp / (ylevels >> 1)
    elif INPUT_DATA_IS_FLOAT:
        fname = 'scope_0.csv'
        sample_freq = 1 * 1000 * 1000 * 1000
        
        #fname = 'scope_5.csv'
        #sample_freq = 1 * 1000 * 1000 * 1000
        
        fdir = os.path.join('..', 'Data')
        fpath = os.path.join(fdir, fname)
        print("DEBUG: csv: {}".format(fpath))

        #stage1_xdata, stage1_ydata = get_csv_sample_data(fpath)
        stage1_xdata, stage1_ydata = sample_data.get_data_from_csv(fpath)
        
        xfactor = 1
        yfactor = 1
    else:
        raise Exception("No input specified")
    
    ##------------------------------------------------------------------------

    ##
    ## Stage 1 Processing.
    ## -------------------
    ##   1. min and max peak detection.
    ##   2. calculate effective time-length and effective bandwidth.
    ##   3. get environment measurements.
    ##   4. save and post parameters.
    ##
    
    print("Stage 1.1 -- Peak detection ...")
    
    print("stage1_xdata = {}".format(stage1_xdata.__array_interface__))
    print("stage1_ydata = {}".format(stage1_ydata.__array_interface__))
    
    ## set delta to equivalent of 100us (for +/-100us window)
    delta = 32768
    #delta = 25000
    #delta = sample_freq * 100 // (1000 * 1000)
    print("100us delta = {}".format(delta))
    
    ## ignore peaks near start or end of data to ensure the +/-delta can be used.
    max_idx, max_yval = peak_detect.np_max_peak_detect(stage1_ydata[delta:-delta])
    
    max_idx += delta
    max_xval = stage1_xdata[max_idx]
    
    min_idx, min_yval = peak_detect.np_min_peak_detect(stage1_ydata[delta:-delta])
    min_idx += delta
    min_xval = stage1_xdata[min_idx]
    
    print("Min Peak at {} with value {}".format(min_idx, min_yval))
    print("stage1_xdata = {} ... min:{} ... {}".format(stage1_xdata[:3], stage1_xdata[min_idx-1:min_idx+1+1], stage1_xdata[-3:]))
    print("stage1_ydata = {} ... min:{} ... {}".format(stage1_ydata[:3], stage1_ydata[min_idx-1:min_idx+1+1], stage1_ydata[-3:]))
    print("Max Peak at {} with value {}".format(max_idx, max_yval))
    print("stage1_xdata = {} ... max:{} ... {}".format(stage1_xdata[:3], stage1_xdata[max_idx-1:max_idx+1+1], stage1_xdata[-3:]))
    print("stage1_ydata = {} ... max:{} ... {}".format(stage1_ydata[:3], stage1_ydata[max_idx-1:max_idx+1+1], stage1_ydata[-3:]))
    
    ##
    ## FIXME: force start of file, just to test against matlab script.
    ##
    if FIXME_IND_MATLAB_HACK:
        #delta = 1000 // 2     ## 1000 samples.
        delta = 631000 // 2     ## 631000 samples.
        delta = 200000 // 2     ## 200us => +/- 100us.
        #delta = len(stage1_xdata) // 2     ## all samples.
        #min_idx = delta
        #max_idx = delta
        #min_xval = stage1_xdata[min_idx]
        #max_xval = stage1_xdata[max_idx]
        #min_yval = stage1_ydata[min_idx]
        #max_yval = stage1_ydata[max_idx]
        print("DEBUG: FORCE: delta={}, min_idx={}, max_idx={}".format(delta, min_idx, max_idx))
        print("DEBUG: Min Peak at {} with value {}".format(min_idx, min_yval))
        print("DEBUG: Max Peak at {} with value {}".format(max_idx, max_yval))
    
    print("Stage 1.1 -- Complete.")
    
    ##
    ## Convert from sampling domain to real world domain (time, voltage).
    ##
    
    stage1b_xdata = stage1_xdata * xfactor
    stage1b_ydata = stage1_ydata * yfactor
    
    print("stage1b_xdata = {}".format(stage1b_xdata.__array_interface__))
    print("stage1b_ydata = {}".format(stage1b_ydata.__array_interface__))
    print("stage1b_xdata = {} ... min:{} ... {}".format(stage1b_xdata[:3], stage1b_xdata[min_idx-1:min_idx+1+1], stage1b_xdata[-3:]))
    print("stage1b_ydata = {} ... min:{} ... {}".format(stage1b_ydata[:3], stage1b_ydata[min_idx-1:min_idx+1+1], stage1b_ydata[-3:]))
    print("stage1b_xdata = {} ... max:{} ... {}".format(stage1b_xdata[:3], stage1b_xdata[max_idx-1:max_idx+1+1], stage1b_xdata[-3:]))
    print("stage1b_ydata = {} ... max:{} ... {}".format(stage1b_ydata[:3], stage1b_ydata[max_idx-1:max_idx+1+1], stage1b_ydata[-3:]))

    ##
    ## Obtain sub-sample for next processing steps.
    ##
    
    print("Stage 1.2 -- Calculate Effective Time-Length and Effective Bandwidth ...")
    
    
    beg_idx = max_idx - delta
    end_idx = max_idx + delta
    stage2a_xdata = stage1b_xdata[beg_idx:end_idx]
    stage2a_ydata = stage1b_ydata[beg_idx:end_idx]
    
    print("Stage2a range from {}:{}".format(beg_idx, end_idx))
    print("Stage2a_xdata = {} ... {} ... {}".format(stage2a_xdata[:3], stage2a_xdata[delta-1:delta+1+1], stage2a_xdata[-3:]))
    print("Stage2a_ydata = {} ... {} ... {}".format(stage2a_ydata[:3], stage2a_ydata[delta-1:delta+1+1], stage2a_ydata[-3:]))
    print("state2a_xdata = {}".format(stage2a_xdata.__array_interface__))
    print("state2a_ydata = {}".format(stage2a_ydata.__array_interface__))

    ## Convert units subsample from stage1 data.
    
    beg_idx = max_idx - delta
    end_idx = max_idx + delta
    stage2b_xdata = stage1_xdata[beg_idx:end_idx] * xfactor
    stage2b_ydata = stage1_ydata[beg_idx:end_idx] * yfactor
    
    print("Stage2b range from {}:{}".format(beg_idx, end_idx))
    print("Stage2b_xdata = {} ... {} ... {}".format(stage2b_xdata[:3], stage2b_xdata[delta-1:delta+1+1], stage2b_xdata[-3:]))
    print("Stage2b_ydata = {} ... {} ... {}".format(stage2b_ydata[:3], stage2b_ydata[delta-1:delta+1+1], stage2b_ydata[-3:]))
    print("state2b_xdata = {}".format(stage2b_xdata.__array_interface__))
    print("state2b_ydata = {}".format(stage2b_ydata.__array_interface__))

    ##
    ## Convert from sampling domain to real world domain (time, voltage).
    ##
    
    if 1:
        stage2_xdata = stage2a_xdata
        stage2_ydata = stage2a_ydata
    else:
        stage2_xdata = stage2b_xdata
        stage2_ydata = stage2b_ydata

    print("stage2_xdata = {} ... {} ... {}".format(stage2_xdata[:3], stage2_xdata[delta-1:delta+1+1], stage2_xdata[-3:]))
    print("stage2_ydata = {} ... {} ... {}".format(stage2_ydata[:3], stage2_ydata[delta-1:delta+1+1], stage2_ydata[-3:]))
    print("stage2_xdata = {}".format(stage2_xdata.__array_interface__))
    print("stage2_ydata = {}".format(stage2_ydata.__array_interface__))

    print("Stage 1.2 -- Complete,")
    
    ##------------------------------------------------------------------------

    fft_length = 256
    tf_map = tf_map_calculate(tdata=stage2_xdata, ydata=stage2_ydata, sample_freq=sample_freq, fft_length=fft_length)
    print("DEBUG: fft_length = {}, tf_map = {}".format(fft_length, tf_map))

    fft_length = 65536
    tf_map = tf_map_calculate(tdata=stage2_xdata, ydata=stage2_ydata, sample_freq=sample_freq, fft_length=fft_length)
    print("DEBUG: fft_length = {}, tf_map = {}".format(fft_length, tf_map))

    fft_length = 0
    tf_map = tf_map_calculate(tdata=stage2_xdata, ydata=stage2_ydata, sample_freq=sample_freq, fft_length=fft_length)
    print("DEBUG: fft_length = {}, tf_map = {}".format(fft_length, tf_map))

    ##------------------------------------------------------------------------

    ## FIXME: enable return statement if matplotlib not installed on running system.
    ## FIXME: e.g. on ZedBoard, PicoZed, Lime2, etc.
    return

    ##
    ## Plot stage1 data.
    ##
    
    import matplotlib.pyplot as pyplot
    import matplotlib.gridspec as gridspec
    
    pyplot.close('all')
#    fig = pyplot.figure()
    fig = pyplot.figure(num=1, figsize=(12,14))
    gs1 = gridspec.GridSpec(5, 1)
    ax1 = fig.add_subplot(gs1[0])
    ax1b = fig.add_subplot(gs1[1])
    ax2 = fig.add_subplot(gs1[2])
    ax3 = fig.add_subplot(gs1[3])
    ax4 = fig.add_subplot(gs1[4])

    print("Plotting Stage 1 data ...")
    ax1.plot(stage1_xdata, stage1_ydata)
    ax1.set_xlabel('A2D Sample Index')
    ax1.set_ylabel('A2D Sample Value')
    ax1.set_title("{} -- Stage 1".format(fpath))
    ax1.grid(True)
    area = np.pi * (20 * 20)    ## PI * r^2
    col = ['red', 'cyan']
    alpha = 0.2
    ax1.scatter([max_xval, min_xval], [max_yval, min_yval], s=area, c=col, alpha=alpha)
    
    ##------------------------------------------------------------------------

    ##
    ## Plot stage1b data.
    ##
    
    max_idx, max_yval = peak_detect.np_max_peak_detect(stage1b_ydata)
    max_xval = stage1b_xdata[max_idx]
    
    min_idx, min_yval = peak_detect.np_min_peak_detect(stage1b_ydata)
    min_xval = stage1b_xdata[min_idx]
    
    print("Plotting Stage 1b data ...")
    ax1b.plot(stage1b_xdata, stage1b_ydata)
    ax1b.set_xlabel('time (s)')
    ax1b.set_ylabel('voltage (V)')
    ax1b.set_title("{} -- Stage 1b".format(fpath))
    ax1b.grid(True)
    ax1b.scatter([max_xval, min_xval], [max_yval, min_yval], s=area, c=col, alpha=alpha)
    
    ##------------------------------------------------------------------------

    ##
    ## Plot stage2 data.
    ##
    
    # Use yellow for min peak of stage2+ data, as it could be a different point than min of stage1 data.
    col = ['red', 'yellow']
    
#    xxx_max_idx, max_yval = peak_detect.np_max_peak_detect(stage2_ydata)
#    max_xval = stage2_xdata[max_idx]
    
    min_idx, min_yval = peak_detect.np_min_peak_detect(stage2_ydata)
    min_xval = stage2_xdata[min_idx]
    
    print("Plotting Stage 2 data ...")
#    pyplot.subplot(2, 1, 2)
    ax2.plot(stage2_xdata, stage2_ydata)
    ax2.set_xlabel('time (s)')
#    ax2.xlabel('A2D Sample Count')
    ax2.set_ylabel('voltage (V)')
#    ax2.ylabel('A2D Sample Value')
    ax2.set_title("{} -- Stage 2".format(fpath))
    ax2.grid(True)
    ax2.scatter([max_xval, min_xval], [max_yval, min_yval], s=area, c=col, alpha=alpha)
#    pyplot.show()

    ##------------------------------------------------------------------------

    delta /= 10
    beg_idx = max_idx - delta
    end_idx = max_idx + delta
    stage3_xdata = stage1b_xdata[beg_idx:end_idx]
    stage3_ydata = stage1b_ydata[beg_idx:end_idx]
    min_idx, min_yval = peak_detect.np_min_peak_detect(stage3_ydata)
    min_xval = stage3_xdata[min_idx]
    
    print("Plotting Stage 3 data ...")
    ax3.plot(stage3_xdata, stage3_ydata)
    ax3.set_xlabel('time (s)')
    ax3.set_ylabel('voltage (V)')
    ax3.set_title("{} -- Stage 2".format(fpath))
    ax3.grid(True)
    ax3.scatter([max_xval, min_xval], [max_yval, min_yval], s=area, c=col, alpha=alpha)

    ##------------------------------------------------------------------------

    delta /= 10
    beg_idx = max_idx - delta
    end_idx = max_idx + delta
    stage4_xdata = stage1b_xdata[beg_idx:end_idx]
    stage4_ydata = stage1b_ydata[beg_idx:end_idx]
    min_idx, min_yval = peak_detect.np_min_peak_detect(stage4_ydata)
    min_xval = stage4_xdata[min_idx]
    
    print("Plotting Stage 4 data ...")
    ax4.plot(stage4_xdata, stage4_ydata)
    ax4.set_xlabel('time (s)')
    ax4.set_ylabel('voltage (V)')
    ax4.set_title("{} -- Stage 2".format(fpath))
    ax4.grid(True)
    ax4.scatter([max_xval, min_xval], [max_yval, min_yval], s=area, c=col, alpha=alpha)

#    pyplot.tight_layout()
    gs1.tight_layout(fig)
    pyplot.show()


if __name__ == "__main__":
    main()

