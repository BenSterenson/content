This playbook runs the whois enrichment on domain indicators provided by an indicator query such as "type:Domain". The playbook then compares the domain registrars against the Cortex XSOAR list provided in the inputs.

## Dependencies
This playbook uses the following sub-playbooks, integrations, and scripts.

### Sub-playbooks
This playbook does not use any sub-playbooks.

### Integrations
* Whois1

### Scripts
* SetAndHandleEmpty
* FilterByList

### Commands
* whois

## Playbook Inputs
---

| **Name** | **Description** | **Default Value** | **Required** |
| --- | --- | --- | --- |
| Indicator Query | Indicators matching the indicator query will be used as playbook input |  | Optional |
| ApprovedRegistrarsListName | The Cortex XSOAR list name that contains the approved registrars. |  | Optional |
| RegistrarListDelimiter | A one\-character string used to delimit fields. This must match the value that you defined in the list separator server configuration.  
The default value is a comma, however, as registrars might contain the "," character in their name, 
Cortex XSOAR recommends that you select a different delimiter. |  | Optional |

## Playbook Outputs
---

| **Path** | **Description** | **Type** |
| --- | --- | --- |
| NonApprovedDomains | Domains for which the registrar isn't approved. | string |
| ApprovedDomains | Domains for which the registrar is approved. | string |

## Playbook Image
---
![Playbook Image](https://raw.githubusercontent.com/demisto/content/883f89fdd8ab1c85fced632d513abcf28d0ec155/Packs/Whois/doc_files/TIM_-_Process_Domain_Registrar_With_WHOIS.png)