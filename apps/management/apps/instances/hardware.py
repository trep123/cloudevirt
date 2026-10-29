import base64

from rest_framework import serializers

from apps.accounts.roles import is_admin


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('����Ϊ���ö���')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: '��֧�ִ�����' for key in unknown})
        return super().to_internal_value(data)


class HardwareSerializer(StrictInput):
    video_model = serializers.ChoiceField(choices=['vga', 'virtio'], required=False)
    video_width = serializers.IntegerField(min_value=640, max_value=3840, required=False)
    video_height = serializers.IntegerField(min_value=480, max_value=2160, required=False)
    cpu_mode = serializers.ChoiceField(choices=['host-model', 'host-passthrough'], required=False)
    sockets = serializers.IntegerField(min_value=1, max_value=128, required=False)
    cores = serializers.IntegerField(min_value=1, max_value=128, required=False)
    threads = serializers.IntegerField(min_value=1, max_value=128, required=False)
    firmware = serializers.ChoiceField(choices=['bios', 'uefi'], required=False)
    secure_boot = serializers.BooleanField(required=False)
    tpm = serializers.BooleanField(required=False)
    cpu_quota_percent = serializers.IntegerField(min_value=0, max_value=12800, required=False)
    disk_read_iops = serializers.IntegerField(min_value=0, max_value=1000000, required=False)
    disk_write_iops = serializers.IntegerField(min_value=0, max_value=1000000, required=False)
    network_mbps = serializers.IntegerField(min_value=0, max_value=100000, required=False)

    def validate(self, data):
        if ('video_width' in data) != ('video_height' in data):
            raise serializers.ValidationError('�Կ��ֱ�����ͬʱָ�����Ⱥ͸߶�')
        if 'video_width' in data and not data.get('video_model'):
            raise serializers.ValidationError('����ȷѡ���Կ��ͺ�')
        parts = ['sockets', 'cores', 'threads']
        if any(key in data for key in parts) and not all(key in data for key in parts):
            raise serializers.ValidationError('CPU ������ͬʱ�ṩ��ۡ����ļ��߳�')
        if data.get('secure_boot') and data.get('firmware') != 'uefi':
            raise serializers.ValidationError('Secure Boot ��Ҫ UEFI')
        return data


class StaticNetworkSerializer(StrictInput):
    pool = serializers.IntegerField(min_value=1)
    address = serializers.IPAddressField(protocol='IPv4', required=False)
    default_route = serializers.BooleanField(required=False)


class InitializationSerializer(StrictInput):
    hostname = serializers.RegexField(
        r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$', required=False
    )
    username = serializers.RegexField(r'^[a-z_][a-z0-9_-]{0,30}$', default='cloudvirt')
    ssh_public_keys = serializers.ListField(
        child=serializers.CharField(max_length=8192), min_length=1, max_length=16
    )

    def validate_username(self, value):
        if value == 'root':
            raise serializers.ValidationError('��ʹ����ͨ�û�����Ҫʱͨ�� sudo ��Ȩ')
        return value

    def validate_ssh_public_keys(self, keys):
        if sum(len(key.encode('utf-8')) for key in keys) > 32768:
            raise serializers.ValidationError('SSH ��Կ�ܳ��Ȳ��ܳ��� 32 KiB')
        for key in keys:
            parts = key.split()
            if (
                '\n' in key
                or '\r' in key
                or len(parts) < 2
                or parts[0]
                not in [
                    'ssh-ed25519',
                    'ssh-rsa',
                    'ecdsa-sha2-nistp256',
                    'ecdsa-sha2-nistp384',
                    'ecdsa-sha2-nistp521',
                ]
            ):
                raise serializers.ValidationError('SSH ��Կ��ʽ��Ч')
            try:
                blob = base64.b64decode(parts[1], validate=True)
            except ValueError:
                raise serializers.ValidationError('SSH ��Կ������Ч') from None
            if (
                len(blob) < 8
                or len(blob) > 8192
                or int.from_bytes(blob[:4]) != len(parts[0])
                or blob[4 : 4 + len(parts[0])] != parts[0].encode()
            ):
                raise serializers.ValidationError('SSH ��Կ������Ч')
        return list(dict.fromkeys(keys))


def validate_hardware_policy(data, user):
    hardware = data.get('hardware', {})
    if (
        'sockets' in hardware
        and hardware['sockets'] * hardware['cores'] * hardware['threads'] != data['vcpu']
    ):
        raise serializers.ValidationError({'hardware': 'CPU ���˳˻�������� vCPU ����'})
    if hardware.get('cpu_quota_percent', 0) > data['vcpu'] * 100:
        raise serializers.ValidationError({'hardware': 'CPU �޶�ܳ�������� vCPU'})
    performance = ['cpu_quota_percent', 'disk_read_iops', 'disk_write_iops', 'network_mbps']
    if any(hardware.get(key, 0) > 0 for key in performance) and not is_admin(user):
        from apps.templates.models import TemplateVersion
        from apps.templates.versions import visible_templates

        version = TemplateVersion.objects.filter(
            pk=data.get('template_version'), published=True, template__in=visible_templates(user)
        ).first()
        if not (
            version
            and 'hardware' in version.constraints.get('locked', [])
            and version.configuration.get('hardware') == hardware
        ):
            raise serializers.ValidationError({'hardware': '���ܵ��Ž�ƽ̨����Ա������'})
    if data.get('initialization') and (
        data['image'].format == 'ISO' or not data['image'].supports_cloud_init
    ):
        raise serializers.ValidationError({'initialization': '����δ������Աȷ��֧�� cloud-init'})


def validate_creation_capabilities(data, capabilities):
    if data.get('static_networks') and capabilities.get('static_networks') is not True:
        raise serializers.ValidationError(
            {'static_networks': '�ڵ���δ��ɾ�̬�����ʼ��Э�飬�ݲ��ܴ�����̬��ַʵ��'}
        )
    hardware = data.get('hardware', {})
    errors = {}
    if hardware.get('video_model') and hardware['video_model'] not in capabilities.get(
        'video_models', []
    ):
        errors['hardware.video_model'] = '�ڵ�δȷ��֧�ִ��Կ�'
    if data.get('data_disks') and capabilities.get('multi_disk') is not True:
        errors['data_disks'] = '�ڵ� Agent δʵ�ֶ����'
    if data.get('additional_networks') and capabilities.get('multi_nic') is not True:
        errors['additional_networks'] = '�ڵ� Agent δʵ�ֶ�����'
    mode = hardware.get('cpu_mode') or ('host-model' if 'sockets' in hardware else None)
    if mode and mode not in capabilities.get('cpu_modes', []):
        errors['hardware.cpu_mode'] = '�ڵ�δȷ��֧�ִ� CPU ģʽ'
    if hardware.get('firmware', 'bios') not in capabilities.get('firmware', ['bios']):
        errors['hardware.firmware'] = '�ڵ�δȷ��֧�ִ˹̼�'
    if hardware.get('secure_boot') and capabilities.get('secure_boot') is not True:
        errors['hardware.secure_boot'] = '�ڵ�δȷ��֧�� Secure Boot'
    if hardware.get('tpm') and capabilities.get('tpm_emulator') is not True:
        errors['hardware.tpm'] = '�ڵ�δȷ��֧�� TPM ģ����'
    if data.get('initialization') and capabilities.get('cloud_init') is not True:
        errors['initialization'] = '�ڵ�δ��װ��ʼ�����ʹ���'
    if errors:
        raise serializers.ValidationError(errors)
