
# Reporting

The Joulescope UI now performs error reporting.  When an error is detected,
the UI will catch the exception and generate an error report.  The UI
prompts the user for contact information and a description, and then
allows the user to submit the error report.

The error report is published to an AWS S3 bucket.  On S3 file creation,
we have configured AWS to use SNS to notify support.


## AWS documentation

* https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-actions.html
* https://aws.amazon.com/blogs/compute/uploading-to-amazon-s3-directly-from-a-web-or-mobile-application/
* https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-s3-object-created-tutorial.html


## AWS stackless application

* [fork](https://github.com/mliberty1/amazon-s3-presigned-urls-aws-sam)
* [orig](https://github.com/aws-samples/amazon-s3-presigned-urls-aws-sam)

stack-name: joulescope-ui-report

    sam deploy
    wget https://k9x78sjeqi.execute-api.us-east-1.amazonaws.com/uploads?token=...
