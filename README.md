### Smart Queries

Whenever we analyze the performance of any API built using Django, and try to find out what is slowing down APIs. Two major reasons are very frequent
* No Index on frequently used columns
* Having N+1 queries on related objects.

N+1 database queries are caused by accessing related objects, for each related object we might have a duplicate query running. These can be easily avoided by using `select_related` or `prefetch_related`

There is no way until we want to explicitly analyze the API endpoints for these performance bottlenecks. This package solves the problem by keeeping a track of all requests and queries happening on them. Each request has SQL Queries seperately recorded with number of 'similar_count' which indicates the N+1 issue.

In short, Repeat Queries is a django package which helps django developer to avoid the N+1 queries issue by recording it and keeping a track of it per request. So that Developers can see the queries for each API on a central dashboard.


This repo contains the demo for repeat query, as well as the django package. 

-----
Installing the smart-queries django package


Installation
-----------
1. The package smart-queries can be installed using

    ```pip install smart-queries ```


2. Add "repeat_queries" to your INSTALLED_APPS setting like this::

    ```
    INSTALLED_APPS = [
        ...
        'repeat_queries',
    ]
    ```
3. Add `repeat_queries.middleware.DuplicateQueryMiddleware`, to your MIDDLEWARE settings like this : 
    ```
    MIDDLEWARE = [
        ...,
        'repeat_queries.middleware.DuplicateQueryMiddleware',
    ]
    ```


4. Run `python manage.py migrate` to create the repeat_queries models.

5. Start the development server, Hit any endpoint/view and visit http://127.0.0.1:8000/admin/ to see your data.


-------
The Django project itself can be run for the demo purpose

```
git clone https://github.com/siddhism/smart-queries
cd smart-queries
virtualenv env_smartquery
source env_smartquery/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

* Create some posts and authors
* Hit the home page with 
http://127.0.0.1:8000/blog/
* Check Admin page for all data
http://127.0.0.1:8000/admin/
