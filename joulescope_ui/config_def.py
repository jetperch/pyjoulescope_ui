# Python format allowed since does not change in the field.
# * json5 format: https://json5.org/ (original selection)
# * TOML: standardized INI, https://github.com/toml-lang/toml
# * YAML: whitespace significant, end-user challenges
# * StrictYaml: https://github.com/crdoconnor/strictyaml
# * JSON: no comments!
CONFIG = {
  'info': {
    'name': 'Joulescope UI configuration file validator',
    'version': 1
  },

  'children':
  [
    # to support UI editing, only 2 levels supported
    {
      'name': 'General',
      'brief': 'Default file locations',
      'type': 'map',
      'children': [
        {
          'name': 'data_path',
          'brief': 'Default data directory',
          'type': 'path',
          'attributes': ['exists', 'dir'],
          'default': '__SAVE_PATH__',
        },
        {
          'name': 'update_check',
          'brief': 'Automatically check for software updates',
          'type': 'bool',
          'default': True,
        },
        {
          'name': 'log_level',
          'brief': 'The logging level',
          'type': 'str',
          'options': ['OFF', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'ALL'],
          'default': 'INFO',
        },
      ]
    },  # General end

    {
      'name': 'Device',
      'brief': 'Joulescope device-specific default settings',
      'type': 'map',
      'children': [

        {
          'name': 'autostream',
          'brief': 'Start streaming when the device connects',
          'type': 'bool',
          'default': True,
        },

        {
          'name': 'source',
          'brief': 'Select the streaming data source',
          'detail': 'Do not edit this setting for normal use',
          'type': 'str',
          'options': ['off', 'raw', 'pattern_usb', 'pattern_control', 'pattern_sensor'],
          'default': 'raw',
        },

        {
          'name': 'i_range',
          'brief': 'Select the current measurement range (shunt resistor)',
          'type': 'str',
          'options': [
            {
              'name': 'auto',
              'brief': 'Perform fast autoranging to select the best shunt value',
            },
            {
              'name': 'off',
              'brief': 'Disable the shunt for high impedance',
            },
            {
              'name': '10 A',
              'brief': 'Least resistance (highest current range)',
              'aliases': ['0'],
            },
            {
              'name': '2 A',
              'aliases': ['1'],
            },
            {
              'name': '180 mA',
              'aliases': ['2'],
            },
            {
              'name': '18 mA',
              'aliases': ['3'],
            },
            {
              'name': '1.8 mA',
              'aliases': ['4'],
            },
            {
              'name': '180 µA',
              'aliases': ['5'],
            },
            {
              'name': '18 µA',
              'brief': 'Most resistance (lowest current range)',
              'aliases': ['6']
            }
          ],
          'default': 'auto'
        },

        {
          'name': 'v_range',
          'brief': 'Select the voltage measurement range (gain)',
          'type': 'str',
          'options': [
            {
              'name': '15V',
              'brief': '15V range (recommended)',
              'aliases': ['high'],
            },
            {
              'name': '5V',
              'brief': '5V range with improved resolution for lower voltages',
              'aliases': ['low'],
            }
          ],
          'default': 'high'
        },

        {
          'name': 'rescan_interval',
          'brief': 'The manual device rescan interval in seconds',
          'detail': 'Device rescan normally happens when devices are connected \
to the computer.  For long running-tests, selecting an additional manual \
rescan interval assists recovery on USB and device failures.  However, \
enabling this feature automatically selects a device on Device->disable.',
          'type': 'str',
          'options': ['off', '1', '2', '5', '10', '20', '50'],
          'default': 'off',
        },

        {
          'name': 'firmware_update',
          'brief': 'Firmware update settings.',
          'type': 'str',
          'options': ['never', 'auto', 'always'],
          'default': 'auto'
        },

        {
          'name': 'on_close',
          'brief': 'Device configuration on device close.',
          'type': 'str',
          'options': ['keep', 'sensor_off', 'current_off', 'current_auto'],
          'default': 'keep',
        },

        {
          'name': 'buffer_duration',
          'brief': 'The stream buffer duration in seconds.',
          'detail': 'Use care when setting this value. \
The software requires 1.5 GB of RAM for every 60 seconds.',
          'type': 'str',
          'options': ['15', '30', '60', '90', '120', '180', '240', '300'],
          'default': '30',
        },
      ]
    }, # Device end

    {
      'name': 'GPIO',
      'brief': 'Joulescope device GPIO settings',
      'type': 'map',
      'children': [
        {
          'name': 'io_voltage',
          'brief': 'The GPI/O high-level voltage.',
          'type': 'str',
          'options': ['1.8V', '2.1V', '2.5V', '2.7V', '3.0V', '3.3V', '5.0V'],
          'default': '3.3V',
        },

        {
          'name': 'gpo0',
          'brief': 'The GPO bit 0 output value.',
          'type': 'str',
          'options': ['0', '1'],
          'default': '0',
        },

        {
          'name': 'gpo1',
          'brief': 'The GPO bit 1 output value.',
          'type': 'str',
          'options': ['0', '1'],
          'default': '0',
        },

        {
          'name': 'current_lsb',
          'brief': 'The current signal least-significant bit mapping.',
          'type': 'str',
          'options': ['normal', 'gpi0'],
          'default': 'normal',
        },

        {
          'name': 'voltage_lsb',
          'brief': 'The voltage signal least-significant bit mapping.',
          'type': 'str',
          'options': ['normal', 'gpi1'],
          'default': 'normal',
        },
      ],
    },

    {
      'name': 'Waveform',
      'brief': 'Waveform display settings',
      'type': 'map',
      'children': [
        {
          'name': 'show_min_max',
          'brief': 'Display the minimum and maximum for ease of finding short events.',
          'type': 'str',
          'options': [
            {
              'name': 'off',
              'brief': 'Hide the min/max indicators',
              'aliases': [False],
            },
            {
              'name': 'lines',
              'brief': 'Display minimum and maximum lines',
              'aliases': [True],
            },
            {
              'name': 'fill',
              'brief': 'Fill the region between min and max, but may significantly reduce performance.',
            },
          ],
          'default': 'lines',
        },

        {
          'name': 'grid_x',
          'brief': 'Display the x-axis grid',
          'type': 'bool',
          'default': True,
        },

        {
          'name': 'grid_y',
          'brief': 'Display the y-axis grid',
          'type': 'bool',
          'default': True,
        },

        {
          'name': 'trace_width',
          'brief': 'The trace width in pixels',
          'detail': 'Increasing trace width SIGNIFICANTLY degrades performance',
          'type': 'str',
          'options': ['1', '2', '4', '6', '8'],
          'default': '1'
        },
      ],
    }, # Waveform end


    {
      'name': 'Developer',
      'brief': 'Developer settings',
      'type': 'map',
      'children': [
        {
          'name': 'compliance',
          'brief': 'Compliance testing mode',
          'type': 'bool',
          'default': False,
        },
        {
          'name': 'compliance_gpio_loopback',
          'brief': 'GPI/O loopback for compliance testing',
          'type': 'bool',
          'default': False,
        }
      ],
    }, # Developer end

  ]
}
