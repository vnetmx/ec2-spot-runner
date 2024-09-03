import boto3
import os
import base64

ec2 = boto3.client('ec2')

ami = os.environ.get('AMI_ID', None)
instance_type = os.environ.get('INSTANCE_TYPE', None)
subnet_id = os.environ.get('SUBNET_ID', None)
security_group = os.environ.get('SECURITY_GROUP', None)
iam_role = os.environ.get('IAM_ROLE_NAME', None)
action = os.environ.get('ACTION', 'start')
instance_id = os.environ.get('INSTANCE_ID', None)
github_token = os.environ.get('GITHUB_TOKEN', None)
github_org = os.environ.get('GITHUB_ORG', None)
github_repo = os.environ.get('GITHUB_REPO', None)
github_runner_extracli = os.environ.get('GITHUB_RUNNER_EXTRACLI', '')
github_runner_label = os.environ.get('GITHUB_RUNNER_LABELS', 'autoscaling,x64,linux')
github_runner_group = os.environ.get('GITHUB_RUNNER_GROUP', 'infra')
max_execution_time = os.environ.get('MAX_EXEC', '60')
github_action_runner_version = os.environ.get('GH_VERSION', '2.319.1')
job_name = os.environ.get('JOB_NAME', None)
job_id = os.environ.get('JOB_ID', None)


# Default user data script to update packages
default_user_data = f"""#!/bin/bash
shutdown -P {max_execution_time}
CURRENT_PATH=$(pwd)

## Max execution time script
echo "./config.sh remove --token {github_token} || true" > $CURRENT_PATH/shutdown_script.sh
echo "shutdown -P +1" > $CURRENT_PATH/shutdown_script.sh
chmod +x $CURRENT_PATH/shutdown_script.sh

## Termiantion script
echo "./config.sh remove --token {github_token} || true" > $CURRENT_PATH/shutdown_now_script.sh
echo "shutdown -h now" > $CURRENT_PATH/shutdown_now_script.sh
chmod +x $CURRENT_PATH/shutdown_now_script.sh

export ACTIONS_RUNNER_HOOK_JOB_COMPLETED=$CURRENT_PATH/shutdown_script.sh
mkdir -p actions-runner && cd actions-runner
echo "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=$CURRENT_PATH/shutdown_script.sh" > .env

GH_RUNNER_VERSION={github_action_runner_version}

case $(uname -m) in aarch64) ARCH="arm64" ;; amd64|x86_64) ARCH="x64" ;; esac && export RUNNER_ARCH=$ARCH

curl -O -L https://github.com/actions/runner/releases/download/v$GH_RUNNER_VERSION/actions-runner-linux-$RUNNER_ARCH-$GH_RUNNER_VERSION.tar.gz

tar xzf ./actions-runner-linux-$RUNNER_ARCH-$GH_RUNNER_VERSION.tar.gz
export RUNNER_ALLOW_RUNASROOT=1
RUNNER_NAME={job_id}-{job_name}-gh

[ -n \"$(command -v yum)\" ] && yum install libicu -y
./config.sh --unattended  --disableupdate --ephemeral --url https://github.com/{github_org} --token {github_token} --labels {github_runner_label} --name $RUNNER_NAME {github_runner_extracli} --runnergroup {github_runner_group}
# timeout={max_execution_time*60};
# found=0;
# (
#     while ((timeout-- > 0)); do
#     [[ -d "_work" ]] && {{ found=1; break; }};
#     sleep 1;
#     done;
#     [[ $found -eq 0 ]] && ../shutdown_now_script.sh
# ) &
./run.sh
"""

user_data = os.environ.get('USER_DATA', default_user_data)
print(user_data)
def create_instance():
    response = ec2.run_instances(
        ImageId=ami,
        InstanceType=instance_type,
        SubnetId=subnet_id,
        SecurityGroupIds=[security_group],
        IamInstanceProfile={'Name': iam_role},
        UserData=base64.b64encode(user_data.encode()).decode(),
        MaxCount=1,
        MinCount=1,
        InstanceInitiatedShutdownBehavior='terminate',
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': f'{job_id}-gh'
                    },
                    {
                        'Key': 'Owner',
                        'Value': 'Infra'
                    },
                    {
                        'Key': 'Project',
                        'Value': 'GitHub Actions'
                    },
                    {
                        'Key': 'JobId',
                        'Value': f'{job_id}'
                    },
                    {
                        'Key': 'JobName',
                        'Value': f'{job_name}'
                    }
                ]
            },
        ],
    )
    _instance_id = response['Instances'][0]['InstanceId']
    print(f"Creating instance {_instance_id}...")

    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[_instance_id])
    print(f"Instance {_instance_id} is now running")
    return _instance_id

def start_instance(instance_id: str) -> None:
    ec2.start_instances(InstanceIds=[
        instance_id,
    ]).start()
    print(f"Started instance {instance_id}")

def stop_instance(instance_id: str) -> None:
    ec2.stop_instances(InstanceIds=[
        instance_id,
    ]).stop()
    print(f"Stopped instance {instance_id}")

if action == 'create':
    create_instance()
elif action == 'start' and instance_id:
    start_instance(instance_id)
elif action == 'stop' and instance_id:
    stop_instance(instance_id)
else:
    print("Invalid action or missing instance ID")
