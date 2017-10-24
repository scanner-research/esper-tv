# Getting started with Google Cloud

This guide will walk you through setting up Esper on Google Cloud. You will need to have a Google account.

**Warning: this guide will help you create a SQL server and Esper web server. You will be billed for the instances.**

## 1. Install the Cloud SDK

On your local machine (laptop/desktop), follow the instructions here to install Google's Cloud SDK: [https://cloud.google.com/sdk/downloads](https://cloud.google.com/sdk/downloads)

## 2. Create a project

Pick a project ID for your application, e.g. `my-esper-project`. Then run:
```bash
gcloud projects create <project ID>
```

## 3. Configure your default region

All databases/servers are created in some region. You should pick the region that's closest to you (but the more important thing is to be consistent--all resources should be in the same region/zone). You can find a list of regions and zone here: [https://cloud.google.com/compute/docs/regions-zones/](https://cloud.google.com/compute/docs/regions-zones/)

Pick a region/zone and run:
```
gcloud compute project-info add-metadata --metadata google-compute-default-region=<your region>,google-compute-default-zone=<your zone>
```

## 3. Enable administration APIs
You will need to explicitly enable the Cloud SQL and IAM (user management) APIs for the subsequent commands to work. Go to the following pages and click "Enable".
* [https://console.developers.google.com/apis/library/sqladmin.googleapis.com/](https://console.developers.google.com/apis/library/sqladmin.googleapis.com/)
* [https://console.developers.google.com/apis/library/iam.googleapis.com/](https://console.developers.google.com/apis/library/iam.googleapis.com/)

## 4. Setup a service account
A service account allows your Esper server to use Google services without requiring your own password. Make sure to replace `<project ID>` with your project ID, and also run this from your local machine:
```
gcloud iam service-accounts create esper --display-name "Esper"
gcloud projects add-iam-policy-binding <project ID> --member serviceAccount:esper@<project ID>.iam.gserviceaccount.com --role roles/editor
```

## 5. Create a SQL database
The SQL database will host all of your Esper metadata. Pick a username and password for your database. Create the database by running:
```
gcloud sql instances create esper-db --database-version=POSTGRES_9_6 --cpu=2 --memory=8GB
gcloud sql databases create esper --instance esper-db
gcloud sql users create <username> '%' --instance esper-db --password <password>
```

## 6. Create a Compute Engine instance
You will need a server to run the Esper website. You could do this locally, but we will also show you how to do it on Google Compute Engine. Make sure to replace `<project ID>` with your project ID from step 2.
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

This will create

If you then run
```
gcloud compute instances list
```

You will find the external IP for the machine you just created. If you want a static IP for your Esper server, follow the instructions here: [https://cloud.google.com/compute/docs/ip-addresses/reserve-static-external-ip-address](https://cloud.google.com/compute/docs/ip-addresses/reserve-static-external-ip-address)

## 5. Setup the machine
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
```

To run Docker without sudo, you will need to add yourself to the docker group:
```
sudo adduser <your user name on the instance> docker
```

Then install pip:
```
sudo apt-get -y install python-pip
```

Lastly download a key for your service account:
```
gcloud iam service-accounts keys create service-key.json --iam-account=esper@<project ID>.iam.gserviceaccount.com
```

## 6. Install Esper

Follow the instructions in the README: [https://github.com/scanner-research/esper](https://github.com/scanner-research/esper).

Note that you will use `config/google.toml` during the `configure.py` step. You will need to edit the file to update the appropriate values for your project.
