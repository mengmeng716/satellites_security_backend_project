from django.db import models

class TestScenarioConfig(models.Model):
    # 基础关联信息
    start_timestamp = models.CharField(max_length=64, verbose_name="Start Timestamp")
    test_id = models.IntegerField(verbose_name="Test ID")

    # 配置参数
    ConstellationConfig = models.IntegerField(verbose_name="Constellation Config")
    DegradedEdgeRatio = models.FloatField(verbose_name="Degraded Edge Ratio")
    EdgeDisconnectRatio = models.FloatField(verbose_name="Edge Disconnect Ratio")
    EdgeBandwidthMeanDecreaseRatio = models.FloatField(verbose_name="Edge Bandwidth Mean Decrease Ratio")
    EdgeBandwidthDecreaseStd = models.FloatField(verbose_name="Edge Bandwidth Decrease Std")
    PoissonRate = models.FloatField(verbose_name="Poisson Rate")
    MeanIntervalTime = models.FloatField(verbose_name="Mean Interval Time")
    PacketGenerationInterval = models.FloatField(verbose_name="Packet Generation Interval")
    PacketSizeMean = models.FloatField(verbose_name="Packet Size Mean")
    PacketSizeStd = models.FloatField(verbose_name="Packet Size Std")

    # 攻击等级
    StateObservationAttack_level = models.IntegerField(verbose_name="State Observation Attack Level")
    ActionAttack_level = models.IntegerField(verbose_name="Action Attack Level")
    StateTransferAttack_level = models.IntegerField(verbose_name="State Transfer Attack Level")
    RewardAttack_level = models.IntegerField(verbose_name="Reward Attack Level")
    ExperiencePoolAttack_level = models.IntegerField(verbose_name="Experience Pool Attack Level")
    ModelTampAttack_level = models.IntegerField(verbose_name="Model Tamp Attack Level")

    # 新增的场景相似度字段
    scenario_similarity = models.FloatField(null=True, blank=True, verbose_name="Scenario Similarity")
    latest_coverage = models.FloatField(null=True, blank=True, verbose_name="Latest Coverage")
    failure_detection_accuracy = models.FloatField(null=True, blank=True, verbose_name="Failure Detection Accuracy")

    class Meta:
        db_table = "test_scenario_config"
        verbose_name = "Test Scenario Config"
        unique_together = ('start_timestamp', 'test_id')

    def __str__(self):
        return f"{self.start_timestamp}_T{self.test_id}"


class StepEvaluate(models.Model):
    # 基础信息
    start_timestamp = models.CharField(max_length=64, verbose_name="Start Timestamp")
    round_index = models.IntegerField(verbose_name="Round Index")
    test_id = models.IntegerField(verbose_name="Test ID")
    step_index = models.IntegerField(verbose_name="Step Index")

    # 关联至场景配置
    scenario = models.ForeignKey(TestScenarioConfig, on_delete=models.CASCADE, null=True, blank=True, related_name="step_evaluations")

    # 指标与评估分数
    PacketLossRate = models.FloatField(verbose_name="Packet Loss Rate")
    NetworkThroughput = models.FloatField(verbose_name="Network Throughput")
    BandwidthUtilization = models.FloatField(verbose_name="Bandwidth Utilization")
    AvgPacketNodeVisits = models.FloatField(verbose_name="Avg Packet Node Visits")
    CumulativeReward = models.FloatField(verbose_name="Cumulative Reward")
    AverageInferenceTime = models.FloatField(verbose_name="Average Inference Time")
    AverageE2eDelay = models.FloatField(verbose_name="Average E2e Delay")
    AverageHopCount = models.FloatField(verbose_name="Average Hop Count")
    AverageComputingRatio = models.FloatField(verbose_name="Average Computing Ratio")
    ComputingWaitingTime = models.FloatField(verbose_name="Computing Waiting Time")
    AverageEndingReward = models.FloatField(verbose_name="Average Ending Reward")
    failure_score_v2 = models.FloatField(verbose_name="Failure Score V2")
    fused_score = models.FloatField(verbose_name="Fused Score")
    
    # 记录生成时间
    timestamp = models.DateTimeField(verbose_name="Timestamp")

    class Meta:
        db_table = "step_evaluate"
        verbose_name = "Step Evaluation"

    def __str__(self):
        return f"{self.start_timestamp}_R{self.round_index}_T{self.test_id}_S{self.step_index}"


class FailureAnalysis(models.Model):
    # 基础追踪信息
    start_timestamp = models.CharField(max_length=64, verbose_name="Start Timestamp")
    original_round_index = models.IntegerField(null=True, blank=True, verbose_name="Original Round Index")
    original_test_id = models.IntegerField(null=True, blank=True, verbose_name="Original Test ID")
    merged_round_index = models.IntegerField(null=True, blank=True, verbose_name="Merged Round Index")
    merged_test_id = models.IntegerField(null=True, blank=True, verbose_name="Merged Test ID")
    step_evaluation = models.CharField(max_length=128, null=True, blank=True, verbose_name="Step Evaluation Reference")
    
    # 攻击分类与归因分析指标
    true_attack_type = models.CharField(max_length=64, null=True, blank=True, verbose_name="True Attack Type")
    predicted_attack_type = models.CharField(max_length=64, null=True, blank=True, verbose_name="Predicted Attack Type")
    target_field = models.CharField(max_length=64, null=True, blank=True, verbose_name="Target Field")
    target_value = models.FloatField(null=True, blank=True, verbose_name="Target Value")
    predicted_fail_score = models.FloatField(null=True, blank=True, verbose_name="Predicted Fail Score")
    absolute_error = models.FloatField(null=True, blank=True, verbose_name="Absolute Error")

    # 配置参数 (SCENARIO_PARAMETER_NAMES) - 注意这里是归因特征贡献值，为浮点数
    ConstellationConfig = models.FloatField(null=True, blank=True, verbose_name="Constellation Config")
    DegradedEdgeRatio = models.FloatField(null=True, blank=True, verbose_name="Degraded Edge Ratio")
    EdgeDisconnectRatio = models.FloatField(null=True, blank=True, verbose_name="Edge Disconnect Ratio")
    EdgeBandwidthMeanDecreaseRatio = models.FloatField(null=True, blank=True, verbose_name="Edge Bandwidth Mean Decrease Ratio")
    EdgeBandwidthDecreaseStd = models.FloatField(null=True, blank=True, verbose_name="Edge Bandwidth Decrease Std")
    PoissonRate = models.FloatField(null=True, blank=True, verbose_name="Poisson Rate")
    MeanIntervalTime = models.FloatField(null=True, blank=True, verbose_name="Mean Interval Time")
    PacketGenerationInterval = models.FloatField(null=True, blank=True, verbose_name="Packet Generation Interval")
    PacketSizeMean = models.FloatField(null=True, blank=True, verbose_name="Packet Size Mean")
    PacketSizeStd = models.FloatField(null=True, blank=True, verbose_name="Packet Size Std")

    # 攻击等级 - 同样是归因特征贡献值，为浮点数
    StateObservationAttack_level = models.FloatField(null=True, blank=True, verbose_name="State Observation Attack Level")
    ActionAttack_level = models.FloatField(null=True, blank=True, verbose_name="Action Attack Level")
    StateTransferAttack_level = models.FloatField(null=True, blank=True, verbose_name="State Transfer Attack Level")
    RewardAttack_level = models.FloatField(null=True, blank=True, verbose_name="Reward Attack Level")
    ExperiencePoolAttack_level = models.FloatField(null=True, blank=True, verbose_name="Experience Pool Attack Level")
    ModelTampAttack_level = models.FloatField(null=True, blank=True, verbose_name="Model Tamp Attack Level")
    
    # 时间戳
    timestamp = models.DateTimeField(verbose_name="Timestamp")

    class Meta:
        db_table = "failure_analysis"
        verbose_name = "Failure Analysis"

    def __str__(self):
        return f"{self.start_timestamp}_R{self.original_round_index}_T{self.original_test_id}"


class SelfHealing(models.Model):
    # 基础与定位信息
    start_timestamp = models.CharField(max_length=64, verbose_name="Start Timestamp")
    test_id = models.IntegerField(verbose_name="Test ID")
    ConstellationConfig = models.IntegerField(null=True, blank=True, verbose_name="Constellation Config")
    node_id = models.CharField(max_length=64, null=True, blank=True, verbose_name="Node ID")
    
    # 自愈结果与性能
    success = models.BooleanField(null=True, blank=True, verbose_name="Success")
    healing_level = models.IntegerField(null=True, blank=True, verbose_name="Healing Level")
    healing_time = models.FloatField(null=True, blank=True, verbose_name="Healing Time")
    message = models.TextField(null=True, blank=True, verbose_name="Message")
    
    # 攻击特征相关
    fail_score = models.FloatField(null=True, blank=True, verbose_name="Fail Score")
    attack_type = models.IntegerField(null=True, blank=True, verbose_name="Attack Type ID")
    attack_label = models.CharField(max_length=64, null=True, blank=True, verbose_name="Attack Label")
    
    # 自愈综合指标
    total_time = models.FloatField(null=True, blank=True, verbose_name="Total Time")
    final_level = models.IntegerField(null=True, blank=True, verbose_name="Final Level")

    # 记录时间截
    timestamp = models.DateTimeField(verbose_name="Timestamp")

    class Meta:
        db_table = "self_healing"
        verbose_name = "Self Healing"

    def __str__(self):
        return f"{self.start_timestamp}_T{self.test_id}_N{self.node_id}"

class PipelineTask(models.Model):
    task_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, default='running') # running, completed, failed
    current_stage = models.CharField(max_length=50, default='Simulation') # 记录当前在跑哪个算法
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)