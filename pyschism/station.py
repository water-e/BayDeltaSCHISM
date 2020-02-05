#!/usr/bin/env python
import sys
import pandas as pd

if sys.version_info[0] < 3:
    from pandas.compat import u
    from builtins import open, file, str
else:
    u = lambda x: x

import argparse
from vtools.data.timeseries import *

def read_staout(fname,station_infile,reftime,ret_station_in = False,multi=False,elim_default=False):
    """Read a SCHISM staout_* file into a pandas DataFrame
    
    Parameters
    ----------
    fpath : fname
        Path to input staout file
        
    station_infile : str or DataFrame
        Path to station.in file or DataFrame from read_station_in

    reftime : Timestampe
        Start of simulation, time basis for staout file elapse time

    ret_station_in : bool
        Return station_in DataFrame for use, which may speed reading of a second file
        
    multi : bool
        Should the returned data have a multi index for the column with location and sublocation. If False the two are collapsed
        
    elim_default : bool
        If the MultiIndex is collapsed, stations with subloc "default" will be collapsed. Eg. ("CLC","default") becomes "CLC_default"
        
     Returns
     -------    
     Result : DataFrame
         DataFrame with hierarchical index (id,subloc) and columns representing the staout data (collapsed as described above
         
    Examples
    --------

    >>> staout1,station_in = read_staout("staout_1","station.in",reftime=pd.Timestamp(2009,2,10),
                                 ret_station_in = True,multi=False,elim_default=True)
    >>> staout6 = read_staout("staout_6",station_in,reftime=pd.Timestamp(2009,2,10),multi=False,elim_default=True)
                
    """
    if isinstance(station_infile,str):
        station_in = read_station_in(station_infile)
    else: station_in = station_infile
    station_index = station_in.index.copy()
    staout = pd.read_csv(fname,index_col=0,sep="\s+",header=None)
    staout.mask(staout==-999.,inplace=True)
    staout.columns = station_index
    elapsed_datetime(staout,reftime=reftime,inplace=True)
    if not multi:
        if elim_default:
            staout.columns = [f'{loc}_{subloc}' if subloc != 'default' else f'{loc}' for loc,subloc in staout.columns]
        else: [f'{loc}_{subloc}' for loc,subloc in staout.columns]
    return (staout, station_infile) if ret_station_in else staout




station_variables = ["elev", "air pressure", "wind_x", "wind_y",
                     "temp", "salt", "u", "v", "w"]

def read_station_in(fpath):
    """Read a SCHISM station.in file into a pandas DataFrame
    
    .. note:: 
        This only reads the tabular part, and assumes the BayDelta SCHISM format with columns:
        index x y z ! id subloc "Name"
        
        Note that there is no header and the delimiter is a space. Also note that the text beginning with ! 
        is extra BayDeltaSCHISM extra metadata, not required for vanilla SCHISM

     Parameters
     ----------
     fpath : fname
        Path to input station.in style file
        
     Returns
     -------    
     Result : DataFrame
         DataFrame with hierarchical index (id,subloc) and columns x,y,z,name
                
    """

    with open(fpath,'r') as f:
        request = f.readline()
        n_entry = f.readline()
        stations = pd.read_csv(f,sep = "\s+",header=None,
                       names=["index","x","y","z","excl","id","subloc","name"],
                       usecols=["x","y","z","id","subloc","name"],
                       index_col=["id","subloc"],na_values="-",keep_default_na=True)
    return stations



def write_station_in(fpath,station_in,request=None):
    """Write a SCHISM station.in file given a pandas DataFrame of metadata
    
     Parameters
     ----------
     fpath : fname
        Path to output station.in file

     station_in : DataFrame
        DataFrame that has station id, x, y, z, name and subloc labels (id is the station id, index will be autogenerated)

     request :  'all' or list(str)
        List of variables to put in output request from the choices 'elev', 'air pressure', 'wind_x', 'wind_y', 'temp', 'salt', 'u', 'v', 'w'
        or 'all' to include them all
    """
    request_int = [0]*len(station_variables)
    if request == "all": request = ["all"]
    request_str = station_variables if request[0] == "all" else request
    request_int = [(1 if var in request_str else 0) for var in station_variables]    
    dfmerged =station_in.reset_index() 
    dfmerged.index += 1
    dfmerged["excl"] = "!"
    nitem = len(dfmerged)
    # First two lines are a space delimited 1 or 0 for each request then the
    # total number of station requests
    buffer = " ".join([str(x) for x in request_int]) + "\n{}\n".format(nitem)
    # Then the specific requests, here written to a string buffer
    buffer2 = dfmerged.to_csv(None,columns=["x","y","z","excl","id","subloc","name"],index_label="id",
        sep=' ',float_format="%.2f",header=False)
    with open(fpath,"w",newline='') as f: 
        f.write(buffer)
        f.write(u(buffer2))
        #f.write(u(buffer))
        #f.write(u(buffer2))


def read_station_depth(fpath):
    """Read a BayDeltaSCHISM station_depths.csv  file into a pandas DataFrame
    
       The BayDelta SCHISM format has a header and uses "," as the delimiter and has these columns:
       id,subloc,z
       
       The id is the station id, which is the key that joins this file to the station database. 'subloc' is a label that describes
       the sublocation or depth and z is the actual elevation of the instrument
       
       Example might be:
       id,subloc,z
       12345,top,-0.5
       
       Other columns are allowed, but this will commonly merged with the station database file so we avoid column names like 'name' that might collide
        
     Parameters
     ----------
     fpath : fname
        Path to input station.in style file
        
     Returns
     -------    
     Result : DataFrame
         DataFrame with hierarchical index (id,subloc) and data column z
                
    """
   
    df = pd.read_csv(fpath,sep=",",header=0,index_col=["id","subloc"])
    df["z"] = -df.depth
    return df[["z"]]



def read_station_dbase(fpath):
    """Read a BayDeltaSCHISM station data base csv  file into a pandas DataFrame
    
       The BayDelta SCHISM format is open, but expects these columns:
       index x y z ! id subloc "Name"
             
        
     Parameters
     ----------
     fpath : fname
        Path to input station.in style file
        
     Returns
     -------    
     Result : DataFrame
         DataFrame with hierarchical index (id,subloc) and columns x,y,z,name
                
    """
    return  pd.read_csv(fpath,sep=",",header=0,index_col="id")

def merge_station_depth(station_dbase,station_depth,default_z):
    """Merge BayDeltaSCHISM station database with depth file, producing the union of all stations and depths including a default entry for stations with no depth entry            
        
     Parameters
     ----------
     station_dbase : DataFrame 
        This should be the input that has only the station id as an index and includes other metadata like x,y, 

     station_depth : DataFrame 
        This should have (id,subloc) as an index
        
     Returns
     -------    
     Result : DataFrame
         DataFrame that links the information.
                
    """
    
    merged =  station_dbase.reset_index().merge(station_depth.reset_index(),
                left_on="id",right_on="id",
                how='left')
    merged.fillna({"subloc":"default","z": default_z},inplace=True)
    merged.set_index(["id","subloc"],inplace=True)
    
    return merged

def read_obs_links(fpath):
    """Read an obs_links csv file which has comma as delimiter and (id,subloc) as index """
    return pd.read_csv(fpath,sep=",",header=0,index_col=["id","subloc"])


def read_station_out(fpath_base,stationinfo,var=None,start=None):
    if var is None:
        fname = fpath_base
    else:
        try:
            fileno = station_variables.index(var)
        except ValueError:
            raise ValueError("Variable name {} not on list: {}.format(var,station_variables")
        fname = "{}_{:d}".format(fileno)
    data = pandas.read_csv(fpath,var,sep="\s+",index_col=0,
                           header=None,names = stationinfo.index,dtype='d')
    if start is not None:
        data = elapsed_to_date(data)
    return data

def example():
    print(read_station_in("example_station.in"))  
    stations_utm = read_station_dbase("stations_utm.csv")
    print(stations_utm)
    sdepth = read_station_depth("station_depth.csv")
    stations_in = merge_station_depth(stations_utm,sdepth,default_z=-0.5)
    #stations_in = pd.merge(stations_utm,sdepth,how='inner',left_index=True,right_index=True)
    #print(stations_in)
    station_request = ["salt","elev"]
    write_station_in("station.in",stations_in,request=station_request)
    #stations_in = read_station_in("station.in")
    obs_links = read_obs_links("obs_links.csv")
    merged = stations_in.merge(obs_links,left_index=True,right_index=True,how="left")
   
    if True:
        print("**")
        print(obs_links)
        print("**")
        print(stations_in)
        print("**")
        print(stations_utm)
        print("**")
        print(merged)

def convert_db_station_in(outfile="station.in",stationdb="stations_utm.csv",depthdb="station_depth.csv",station_request="all",default=-0.5):
    stations_utm = read_station_dbase(stationdb)
    sdepth = read_station_depth(depthdb)
    stations_in = merge_station_depth(stations_utm,sdepth,default_z=-0.5)
    write_station_in(outfile,stations_in,request=station_request)


def create_arg_parser():
    """ Create an argument parser
    """
    parser = argparse.ArgumentParser(description="Create station.in file from station database (stations_utm.csv) and station depth listing station_depth.csv")
    parser.add_argument('--station_db', default = "stations_utm.csv",
                        help="station database, often stations_utm.csv")
    parser.add_argument('--depth_db', default = "station_depth.csv",
                        help="depth listings for stations (otherwise default depth)")
    parser.add_argument('--request', default='all',nargs="+",help="requested variables or 'all' for all of them. Possibilities are: {}".format(",".join(station_variables)))
    parser.add_argument('--default_zcor',default='-0.5',
                        help="z coordinate used when there is no listing for station id (z coordinate, not depth from surface)")
    parser.add_argument('--out', default = "station.in",
                        help="station.in formatted file")
    return parser


def main():
    """ A main function to convert polygon files
    """
    parser = create_arg_parser()
    args = parser.parse_args()
    stationdb = args.station_db
    depthdb = args.depth_db
    default = args.default_zcor
    request = args.request
    outfile = args.out
    print(request)    
    convert_db_station_in(outfile,stationdb,depthdb,request,default)

if __name__ == '__main__':
    #example()
    main()



