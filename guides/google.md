# Getting started with Google Cloud

This guide will walk you through setting up Esper on Google Cloud. You will need to have a Google account. While walking through this guide, you will create a number of configuration settings (e.g. a project ID). Keep the file `config/google.toml` open and update the values as instructed.

**Warning: this guide will help you create a SQL server and Esper web server. You will be billed for the instances.**


## 1. Install the Cloud SDK

On your local machine (laptop/desktop), follow the instructions here to install Google's Cloud SDK: [https://cloud.google.com/sdk/downloads](https://cloud.google.com/sdk/downloads)


## 2. Create a project

Pick a project ID for your application, e.g. `my-esper-project`. Then run:
```bash
gcloud projects create <project ID>
```

Configure `google.project` to your project ID in `config/google.toml`.


## 3. Configure your default region

All databases/servers are created in some region. You should pick the region that's closest to you (but the more important thing is to be consistent--all resources should be in the same region/zone). You can find a list of regions and zone here: [https://cloud.google.com/compute/docs/regions-zones/](https://cloud.google.com/compute/docs/regions-zones/)

Note that if you intend to use GPUs for video processing, only a select subset of zones contain machines with GPUs. See the list here: [https://cloud.google.com/compute/docs/gpus/](https://cloud.google.com/compute/docs/gpus/)

Pick a region/zone and run:
```
gcloud compute project-info add-metadata --metadata google-compute-default-region=<your region, e.g. us-west1>,google-compute-default-zone=<your zone, e.g. us-west1-b>
```

Configure `google.zone` to your selected zone.


## 4. Enable administration APIs
You will need to explicitly enable the Cloud SQL and IAM (user management) APIs for the subsequent commands to work. Go to the following pages and click "Enable".
* [https://console.developers.google.com/apis/library/sqladmin.googleapis.com/](https://console.developers.google.com/apis/library/sqladmin.googleapis.com/)
* [https://console.developers.google.com/apis/library/iam.googleapis.com/](https://console.developers.google.com/apis/library/iam.googleapis.com/)


## 5. Setup a service account
A service account allows your Esper server to use Google services without requiring your own password. Make sure to replace `<project ID>` with your project ID, and also run this from your local machine:
```
gcloud iam service-accounts create esper --display-name "Esper"
gcloud projects add-iam-policy-binding <project ID> --member serviceAccount:esper@<project ID>.iam.gserviceaccount.com --role roles/editor
```


## 6. Setup a Storage bucket
Google Cloud Storage (GCS) will host all of your large files, namely videos and any derived visual data like image thumbnails. GCS is similar to a normal file system, except:
* You can access your files anywhere on the globe.
* Accessing files is slow. It's recommended only to store large files, not small pieces of metadata (>1MB as a rule of thumb).
* At the top-level, GCS is organized around buckets, which are like normal folders but they specify certain characteristics of the files they contain like in what region of the globe your files will be stored.
* Buckets are *technically* completely flat lists of files. In a normal operating system, files are grouped under folders. However, in GCS, `a/b.txt` is just a filename, the `a/` doesn't actually mean there's a folder. That said, the tooling and web interface still *kind of* ascribe a folder-based structure to your files. [See here for the gory details.](https://cloud.google.com/storage/docs/gsutil/addlhelp/HowSubdirectoriesWork)

First, pick a name for your bucket and create it:
```
gsutil mb -c regional -l <your region, e.g. us-west1> gs://<bucket name>
```

> Note: bucket names have to be globally unique across every Google user, so be creative. We already took `gs://esper` :wink:.

Configure `storage.bucket` with your bucket name. Then pick a "directory" name for Esper-related auto-egnerated files, and configure `storage.path` with that name.

Lastly, you'll want to upload your video files into GCS. It doesn't matter where they are in the bucket, they just need to be in the same bucket.
```
gsutil -m cp -r local_video_dir gs://<bucket name>/videos
```

> Note: GCS does not charge you for ingress (uploading files), but it does charge you for egress (downloading files), so watch your billing. Storage is generally quite cheap, but network costs can rack up.

Once you have videos in cloud storage, if you ever need to reference their paths in the course of using Esper, it should always be relative to the root of the bucket, e.g. `videos/example.mp4`, not `gs://<bucket name>/videos/example.mp4`.


## 7. Create a SQL database
The SQL database will host all of your Esper metadata. Pick a username and password for your database. Create the database by running:
```
gcloud sql instances create esper-db --database-version=POSTGRES_9_6 --cpu=2 --memory=8GB
gcloud sql databases create esper --instance esper-db
gcloud sql users create <username> '%' --instance esper-db --password <password>
```

Configure `database.name`, `database.user`, and `database.password` to your selected values.


## 8. Create a Compute Engine instance
You will need a server to run the Esper website. You could do this locally, but we will also show you how to do it on Google Compute Engine (GCE). Make sure to replace `<project ID>` with your project ID from step 2.
```
gcloud compute instances create esper-server \
    --machine-type "n1-standard-2" \
    --tags "http-server","https-server" \
    --image "ubuntu-1604-xenial-v20171011" \
    --image-project "ubuntu-os-cloud" \
    --boot-disk-size "100" \
    --boot-disk-type "pd-standard" \
    --boot-disk-device-name "esper-server" \
    --service-account "esper@<project ID>.iam.gserviceaccount.com" \
    --scopes "default,storage-rw,sql-admin,cloud-platform"
```


## 9. Setup the machine
First, ssh into the machine by running:
```
gcloud compute ssh esper-server
```

Then while on the machine, install Docker:
```
sudo apt-get -y update
sudo apt-get -y install \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) \
    stable"
sudo apt-get -y update
sudo apt-get -y install docker-ce
sudo adduser $USER docker
```

Then install pip and git:
```
sudo apt-get -y install python-pip git
```

Lastly, clone the Esper repo and download a key for your service account:
```
git clone https://github.com/scanner-research/esper
cd esper
gcloud iam service-accounts keys create service-key.json --iam-account=esper@<project ID>.iam.gserviceaccount.com
```


## 10. Install Esper

Follow the instructions in the [README](https://github.com/scanner-research/esper), replacing `config/local.toml` with `config/google.toml` at the configuration step.

If you then run:
```
gcloud compute instances list
```

You will find the external IP for your machine. Visit the provided external IP in your browser, and you should see a running Esper server. If you want a static IP for your Esper server, [follow the instructions here](https://cloud.google.com/compute/docs/ip-addresses/reserve-static-external-ip-address).
